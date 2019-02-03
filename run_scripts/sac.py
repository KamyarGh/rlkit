import numpy as np
from gym.envs.mujoco import HalfCheetahEnv, InvertedPendulumEnv, ReacherEnv
from gym.spaces import Dict

import rlkit.torch.pytorch_util as ptu
from rlkit.envs.wrappers import NormalizedBoxEnv
from rlkit.launchers.launcher_util import setup_logger, set_seed
from rlkit.torch.sac.policies import ReparamTanhMultivariateGaussianPolicy
from rlkit.torch.sac.sac import NewSoftActorCritic
from rlkit.torch.networks import FlattenMlp

from rlkit.envs import get_env

import yaml
import argparse
import importlib
import psutil
import os
import argparse


def experiment(variant):
    env_specs = variant['env_specs']
    if env_specs['train_test_env']:
        env, training_env = get_env(env_specs)
    else:
        env, _ = get_env(env_specs)
        training_env, _ = get_env(env_specs)

    print(env.observation_space)

    if isinstance(env.observation_space, Dict):
        if not variant['algo_params']['policy_uses_pixels']:
            obs_dim = int(np.prod(env.observation_space.spaces['obs'].shape))
            if variant['algo_params']['policy_uses_task_params']:
                if variant['algo_params']['concat_task_params_to_policy_obs']:
                    obs_dim += int(np.prod(env.observation_space.spaces['obs_task_params'].shape))
                else:
                    raise NotImplementedError()
        else:
            raise NotImplementedError()
    else:
        obs_dim = int(np.prod(env.observation_space.shape))
    action_dim = int(np.prod(env.action_space.shape))

    net_size = variant['net_size']
    qf1 = FlattenMlp(
        hidden_sizes=[net_size, net_size],
        input_size=obs_dim + action_dim,
        output_size=1,
    )
    qf2 = FlattenMlp(
        hidden_sizes=[net_size, net_size],
        input_size=obs_dim + action_dim,
        output_size=1,
    )
    vf = FlattenMlp(
        hidden_sizes=[net_size, net_size],
        input_size=obs_dim,
        output_size=1,
    )
    policy = ReparamTanhMultivariateGaussianPolicy(
        hidden_sizes=[net_size, net_size],
        obs_dim=obs_dim,
        action_dim=action_dim,
    )
    algorithm = NewSoftActorCritic(
        env=env,
        training_env=training_env,
        policy=policy,
        qf1=qf1,
        qf2=qf2,
        vf=vf,
        **variant['algo_params']
    )
    if ptu.gpu_enabled():
        algorithm.cuda()
    algorithm.train()

    return 1


if __name__ == '__main__':
    # Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--experiment', help='experiment specification file')
    args = parser.parse_args()
    with open(args.experiment, 'r') as spec_file:
        spec_string = spec_file.read()
        exp_specs = yaml.load(spec_string)
    
    if exp_specs['use_gpu']:
        print('\n\nUSING GPU\n\n')
        ptu.set_gpu_mode(True)
    exp_id = exp_specs['exp_id']
    exp_prefix = exp_specs['exp_name']
    seed = exp_specs['seed']
    set_seed(seed)
    setup_logger(exp_prefix=exp_prefix, exp_id=exp_id, variant=exp_specs)

    experiment(exp_specs)
