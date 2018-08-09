"""
Common evaluation utilities.
"""

from collections import OrderedDict
from numbers import Number
import os

import numpy as np

from rlkit.core.vistools import plot_returns_on_same_plot 


def get_generic_path_information(paths, stat_prefix=''):
    """
    Get an OrderedDict with a bunch of statistic names and values.
    """
    statistics = OrderedDict()
    returns = [sum(path["rewards"]) for path in paths]

    rewards = np.vstack([path["rewards"] for path in paths])
    statistics.update(create_stats_ordered_dict('Rewards', rewards,
                                                stat_prefix=stat_prefix,
                                                always_show_all_stats=True))
    statistics.update(create_stats_ordered_dict('Returns', returns,
                                                stat_prefix=stat_prefix,
                                                always_show_all_stats=True))
    actions = [path["actions"] for path in paths]
    if len(actions[0].shape) == 1:
        actions = np.hstack([path["actions"] for path in paths])
    else:
        actions = np.vstack([path["actions"] for path in paths])
    statistics.update(create_stats_ordered_dict(
        'Actions', actions, stat_prefix=stat_prefix,
        always_show_all_stats=True
    ))
    statistics['Num Paths'] = len(paths)

    return statistics


def get_average_returns(paths):
    returns = [sum(path["rewards"]) for path in paths]
    return np.mean(returns)


def create_stats_ordered_dict(
        name,
        data,
        stat_prefix=None,
        always_show_all_stats=False,
        exclude_max_min=False,
):
    print('\n<<<< STAT FOR {} {} >>>>'.format(stat_prefix, name))
    if stat_prefix is not None:
        name = "{} {}".format(stat_prefix, name)
    if isinstance(data, Number):
        print('was a Number')
        return OrderedDict({name: data})

    if len(data) == 0:
        return OrderedDict()

    if isinstance(data, tuple):
        print('was a tuple')
        ordered_dict = OrderedDict()
        for number, d in enumerate(data):
            sub_dict = create_stats_ordered_dict(
                "{0}_{1}".format(name, number),
                d,
            )
            ordered_dict.update(sub_dict)
        return ordered_dict

    if isinstance(data, list):
        try:
            iter(data[0])
        except TypeError:
            pass
        else:
            data = np.concatenate(data)

    if (isinstance(data, np.ndarray) and data.size == 1
            and not always_show_all_stats):
        print('was a numpy array of data.size==1')
        return OrderedDict({name: float(data)})

    print('was a numpy array NOT of data.size==1')
    stats = OrderedDict([
        (name + ' Mean', np.mean(data)),
        (name + ' Std', np.std(data)),
    ])
    if not exclude_max_min:
        stats[name + ' Max'] = np.max(data)
        stats[name + ' Min'] = np.min(data)
    return stats


# I (Kamyar) will be adding my own eval utils here too
def plot_experiment_returns(exp_path, title, save_path, y_axis_lims=None):
    '''
        plots the Test Returns Mean of all the
    '''
    arr_list = []
    names = []

    for sub_exp_dir in os.listdir(exp_path):
        sub_exp_path = os.path.join(exp_path, sub_exp_dir)
        if not os.path.isdir(sub_exp_path): continue
        
        csv_full_path = os.path.join(sub_exp_path, 'progress.csv')
        try:
            returns = np.genfromtxt(csv_full_path, skip_header=0, delimiter=',', names=True)['Test_Returns_Mean']
            arr_list.append(returns)
            names.append(sub_exp_dir)
        except:
            pass

    plot_returns_on_same_plot(arr_list, names, title, save_path, y_axis_lims=y_axis_lims)
