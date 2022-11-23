from collections import OrderedDict
from typing import Dict, Optional, Tuple, List

import torch
from torch import Tensor
from torch.linalg import vector_norm
from torch.nn import Conv2d


def zerolize_filters(conv: Conv2d, pruning_ratio: float) -> None:
    """Zerolize filters of convolutional layer to the pruning_ratio (in-place).

    Args:
        conv: The optimizable layer.
        pruning_ratio: pruning hyperparameter, percentage of zerolized filters.
    """
    filter_pruned_num = int(conv.weight.size()[0] * pruning_ratio)
    filter_norms = vector_norm(conv.weight, dim=(1, 2, 3))
    _, indices = filter_norms.sort()
    with torch.no_grad():
        conv.weight[indices[:filter_pruned_num]] = 0


def _check_zero_filters(weight: Tensor) -> Tensor:
    """Returns indices of zero filters."""
    filters = torch.count_nonzero(weight, dim=(1, 2, 3))
    indices = torch.flatten(torch.nonzero(filters))
    return indices


def _prune_filters(
        weight: Tensor,
        saving_filters: Optional[Tensor] = None,
        saving_channels: Optional[Tensor] = None,
) -> Tensor:
    """Prune filters and channels of convolutional layer.

    Args:
        weight: Weight matrix.
        saving_filters: Indexes of filters to be saved.
            If ``None`` all filters to be saved.
        saving_channels: Indexes of channels to be saved.
            If ``None`` all channels to be saved.
    """
    if saving_filters is not None:
        weight = weight[saving_filters].clone()
    if saving_channels is not None:
        weight = weight[:, saving_channels].clone()
    return weight


def _prune_batchnorm(bn: Dict, saving_channels: Tensor) -> Dict[str, Tensor]:
    """Prune BatchNorm2d.

    Args:
        bn: Dictionary with batchnorm params.
        saving_channels: Indexes of channels to be saved.
            If ``None`` all channels to be saved.
    """
    bn['weight'] = bn['weight'][saving_channels].clone()
    bn['bias'] = bn['bias'][saving_channels].clone()
    bn['running_mean'] = bn['running_mean'][saving_channels].clone()
    bn['running_var'] = bn['running_var'][saving_channels].clone()
    return bn


def _index_union(x: Tensor, y: Tensor) -> Tensor:
    """Returns the union of x and y"""
    x = set(x.tolist())
    y = set(y.tolist())
    xy = x | y
    return torch.tensor(list(xy))


def _indexes_of_tensor_values(tensor: Tensor, values: Tensor) -> Tensor:
    """Returns the indexes of the values in the input tensor."""
    indexes = []
    tensor = tensor.tolist()
    for value in values.tolist():
        indexes.append(tensor.index(value))
    return torch.tensor(indexes)


def _parse_resnet_sd(state_dict: OrderedDict):
    """Parses state_dict to nested dictionaries."""
    parsed_sd = OrderedDict()
    for k, v in state_dict.items():
        _parse_resnet_param(k.split('.'), v, parsed_sd)
    return parsed_sd


def _parse_resnet_param(param, value, dictionary):
    """Parses value from state_dict to nested dictionaries."""
    if len(param) > 1:
        dictionary.setdefault(param[0], OrderedDict())
        _parse_resnet_param(param[1:], value, dictionary[param[0]])
    else:
        dictionary[param[0]] = value


def _collect_resnet_sd(parsed_state_dict):
    """Collect state_dict from nested dictionaries."""
    state_dict = OrderedDict()
    keys, values = _collect_resnet_param(parsed_state_dict)
    for k, v in zip(keys, values):
        key = '.'.join(k)
        state_dict[key] = v
    return state_dict


def _collect_resnet_param(dictionary):
    """Collect value from nested dictionaries."""
    if isinstance(dictionary, OrderedDict):
        all_keys = []
        all_values = []
        for k, v in dictionary.items():
            keys, values = _collect_resnet_param(v)
            for key in keys:
                key.insert(0, k)
            all_values.extend(values)
            all_keys.extend(keys)
        return all_keys, all_values
    else:
        return [[]], [dictionary]


def _prune_resnet_block(block: Dict, input_channels: Tensor) -> Tuple[Tensor, Tensor]:
    """Prune block of ResNet"""
    channels = input_channels
    downsample_channels = input_channels
    keys = list(block.keys())
    if 'downsample' in keys:
        filters = _check_zero_filters(block['downsample']['0']['weight'])
        block['downsample']['0']['weight'] = _prune_filters(
            weight=block['downsample']['0']['weight'],
            saving_filters=filters,
            saving_channels=downsample_channels
        )
        downsample_channels = filters
        block['downsample']['1'] = _prune_batchnorm(
            bn=block['downsample']['1'],
            saving_channels=downsample_channels
        )
        keys.remove('downsample')
    final_conv = keys[-2]
    final_bn = keys[-1]
    keys = keys[:-2]
    for key in keys:
        if key.startswith('conv'):
            filters = _check_zero_filters(block[key]['weight'])
            block[key]['weight'] = _prune_filters(
                weight=block[key]['weight'],
                saving_filters=filters,
                saving_channels=channels
            )
            channels = filters
        elif key.startswith('bn'):
            block[key] = _prune_batchnorm(bn=block[key], saving_channels=channels)
    filters = _check_zero_filters(block[final_conv]['weight'])
    filters = _index_union(filters, downsample_channels)
    block[final_conv]['weight'] = _prune_filters(
        weight=block[final_conv]['weight'],
        saving_filters=filters,
        saving_channels=channels,
    )
    channels = filters
    block[final_bn] = _prune_batchnorm(bn=block[final_bn], saving_channels=channels)
    block['indexes'] = _indexes_of_tensor_values(channels, downsample_channels)
    return channels, _indexes_of_tensor_values(channels, downsample_channels)


def prune_resnet_state_dict(
        state_dict: OrderedDict
) -> Tuple[OrderedDict, Dict[str, List[int]], Dict[str, List[int]]]:
    """Prune state_dict of ResNet

    Args:
        state_dict: ``state_dict`` of ResNet model.

    Returns:
        Tuple(state_dict, input_channels, output_channels).
    """
    input_size = {'layer1': [], 'layer2': [], 'layer3': [], 'layer4': []}
    output_size = {'layer1': [], 'layer2': [], 'layer3': [], 'layer4': []}
    sd = _parse_resnet_sd(state_dict)
    filters = _check_zero_filters(sd['conv1']['weight'])
    sd['conv1']['weight'] = _prune_filters(
        weight=sd['conv1']['weight'], saving_filters=filters
    )
    channels = filters
    sd['bn1'] = _prune_batchnorm(bn=sd['bn1'], saving_channels=channels)
    for layer in ['layer1', 'layer2', 'layer3', 'layer4']:
        for k, v in sd[layer].items():
            input_size[layer].append(channels.size()[0])
            channels, index = _prune_resnet_block(block=v, input_channels=channels)
            output_size[layer].append(channels.size()[0])
    sd['fc']['weight'] = sd['fc']['weight'][:, channels].clone()
    sd = _collect_resnet_sd(sd)
    return sd, input_size, output_size
