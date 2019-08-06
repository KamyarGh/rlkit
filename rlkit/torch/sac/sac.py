from collections import OrderedDict

import numpy as np
import torch
from torch import nn as nn
import torch.nn.functional as F
import torch.optim as optim

import rlkit.torch.pytorch_util as ptu
from rlkit.core.trainer import Trainer
from rlkit.core.eval_util import create_stats_ordered_dict


class SoftActorCritic(Trainer):
    """
    version that:
        - uses reparameterization trick
        - has two Q functions and a V function
    Recently in rlkit there is a version which only uses two Q functions
    as well as an implementation of entropy tuning
    """
    def __init__(
            self,
            policy,
            qf1,
            qf2,
            vf,

            reward_scale=1.0,
            discount=0.99,

            policy_lr=1e-3,
            qf_lr=1e-3,
            vf_lr=1e-3,
            soft_target_tau=1e-2,

            policy_mean_reg_weight=1e-3,
            policy_std_reg_weight=1e-3,

            optimizer_class=optim.Adam,
    ):
        self.policy = policy
        self.qf1 = qf1
        self.qf2 = qf2
        self.vf = vf
        self.reward_scale = reward_scale
        self.discount = discount
        self.soft_target_tau = soft_target_tau
        self.policy_mean_reg_weight = policy_mean_reg_weight
        self.policy_std_reg_weight = policy_std_reg_weight

        self.target_vf = vf.copy()
        self.eval_statistics = None

        self.policy_optimizer = optimizer_class(
            self.policy.parameters(),
            lr=policy_lr,
        )
        self.qf1_optimizer = optimizer_class(
            self.qf1.parameters(),
            lr=qf_lr,
        )
        self.qf2_optimizer = optimizer_class(
            self.qf2.parameters(),
            lr=qf_lr,
        )
        self.vf_optimizer = optimizer_class(
            self.vf.parameters(),
            lr=vf_lr,
        )


    def train_step(self, batch):
        rewards = self.reward_scale * batch['rewards']
        terminals = batch['terminals']
        obs = batch['observations']
        actions = batch['actions']
        next_obs = batch['next_observations']

        q1_pred = self.qf1(obs, actions)
        q2_pred = self.qf2(obs, actions)
        v_pred = self.vf(obs)
        # Make sure policy accounts for squashing functions like tanh correctly!
        policy_outputs = self.policy(obs, return_log_prob=True)
        new_actions, policy_mean, policy_log_std, log_pi = policy_outputs[:4]

        """
        QF Loss
        """
        target_v_values = self.target_vf(next_obs)
        q_target = rewards + (1. - terminals) * self.discount * target_v_values
        qf1_loss = 0.5 * torch.mean((q1_pred - q_target.detach())**2)
        qf2_loss = 0.5 * torch.mean((q2_pred - q_target.detach())**2)

        """
        VF Loss
        """
        q1_new_acts = self.qf1(obs, new_actions)
        q2_new_acts = self.qf2(obs, new_actions)
        q_new_actions = torch.min(q1_new_acts, q2_new_acts)
        v_target = q_new_actions - log_pi
        vf_loss = 0.5 * torch.mean((v_pred - v_target.detach())**2)

        """
        Policy Loss
        """
        policy_loss = torch.mean(log_pi - q_new_actions)
        mean_reg_loss = self.policy_mean_reg_weight * (policy_mean**2).mean()
        std_reg_loss = self.policy_std_reg_weight * (policy_log_std**2).mean()
        policy_reg_loss = mean_reg_loss + std_reg_loss
        policy_loss = policy_loss + policy_reg_loss

        """
        Update networks
        """
        self.qf1_optimizer.zero_grad()
        qf1_loss.backward()
        self.qf1_optimizer.step()

        self.qf2_optimizer.zero_grad()
        qf2_loss.backward()
        self.qf2_optimizer.step()

        self.vf_optimizer.zero_grad()
        vf_loss.backward()
        self.vf_optimizer.step()

        self.policy_optimizer.zero_grad()
        policy_loss.backward()
        self.policy_optimizer.step()

        self._update_target_network()

        """
        Save some statistics for eval
        """
        if self.eval_statistics is None:
            """
            Eval should set this to None.
            This way, these statistics are only computed for one batch.
            """
            self.eval_statistics = OrderedDict()
            self.eval_statistics['Reward Scale'] = self.reward_scale
            self.eval_statistics['QF1 Loss'] = np.mean(ptu.get_numpy(qf1_loss))
            self.eval_statistics['QF2 Loss'] = np.mean(ptu.get_numpy(qf2_loss))
            self.eval_statistics['VF Loss'] = np.mean(ptu.get_numpy(vf_loss))
            self.eval_statistics['Policy Loss'] = np.mean(ptu.get_numpy(
                policy_loss
            ))
            self.eval_statistics.update(create_stats_ordered_dict(
                'Q1 Predictions',
                ptu.get_numpy(q1_pred),
            ))
            self.eval_statistics.update(create_stats_ordered_dict(
                'Q2 Predictions',
                ptu.get_numpy(q2_pred),
            ))
            self.eval_statistics.update(create_stats_ordered_dict(
                'V Predictions',
                ptu.get_numpy(v_pred),
            ))
            self.eval_statistics.update(create_stats_ordered_dict(
                'Log Pis',
                ptu.get_numpy(log_pi),
            ))
            self.eval_statistics.update(create_stats_ordered_dict(
                'Policy mu',
                ptu.get_numpy(policy_mean),
            ))
            self.eval_statistics.update(create_stats_ordered_dict(
                'Policy log std',
                ptu.get_numpy(policy_log_std),
            ))


    @property
    def networks(self):
        return [
            self.policy,
            self.qf1,
            self.qf2,
            self.vf,
            self.target_vf,
        ]


    def _update_target_network(self):
        ptu.soft_update_from_to(self.vf, self.target_vf, self.soft_target_tau)


    def get_snapshot(self):
        return dict(
            qf1=self.qf1,
            qf2=self.qf2,
            policy=self.policy,
            vf=self.vf,
            target_vf=self.target_vf,
        )
    

    def get_eval_statistics(self):
        return self.eval_statistics
    

    def end_epoch(self):
        self.eval_statistics = None


# class MetaNewSoftActorCritic(TorchMetaRLAlgorithm):
#     def __init__(
#             self,
#             env,
#             policy,
#             qf1,
#             qf2,
#             vf,

#             train_task_params_sampler,
#             test_task_params_sampler,

#             num_tasks_per_batch=4,
#             num_samples_per_task_per_batch=64,
#             num_tasks_per_eval=4,
#             num_eval_trajs_per_task=10,

#             num_updates_per_train_call=1000,

#             policy_lr=1e-3,
#             qf_lr=1e-3,
#             vf_lr=1e-3,
#             policy_mean_reg_weight=1e-3,
#             policy_std_reg_weight=1e-3,
#             policy_pre_activation_weight=0.,
#             optimizer_class=optim.Adam,

#             soft_target_tau=1e-2,
#             plotter=None,
#             render_eval_paths=False,
#             eval_deterministic=True,

#             do_running_obs_norm=False,
#             true_env_obs_dim=None,

#             **kwargs
#     ):
#         super().__init__(
#             env=env,
#             train_task_params_sampler=train_task_params_sampler,
#             test_task_params_sampler=test_task_params_sampler,
#             **kwargs
#         )
#         if self.policy_uses_pixels: raise NotImplementedError()
#         assert self.policy_uses_task_params, 'Doesn\'t make sense to use this otherwise.'
#         self.main_policy = policy
#         self.qf1 = qf1
#         self.qf2 = qf2
#         self.vf = vf
#         self.soft_target_tau = soft_target_tau
#         self.policy_mean_reg_weight = policy_mean_reg_weight
#         self.policy_std_reg_weight = policy_std_reg_weight
#         self.policy_pre_activation_weight = policy_pre_activation_weight
#         self.plotter = plotter
#         self.render_eval_paths = render_eval_paths

#         self.num_tasks_per_batch = num_tasks_per_batch
#         self.num_samples_per_task_per_batch = num_samples_per_task_per_batch
#         self.num_tasks_per_eval = num_tasks_per_eval
#         self.num_eval_trajs_per_task = num_eval_trajs_per_task

#         self.num_updates_per_train_call = num_updates_per_train_call

#         self.target_vf = vf.copy()
#         self.qf_criterion = nn.MSELoss()
#         self.vf_criterion = nn.MSELoss()
#         self.eval_statistics = None

#         self.policy_optimizer = optimizer_class(
#             self.main_policy.parameters(),
#             lr=policy_lr,
#         )
#         self.qf1_optimizer = optimizer_class(
#             self.qf1.parameters(),
#             lr=qf_lr,
#         )
#         self.qf2_optimizer = optimizer_class(
#             self.qf2.parameters(),
#             lr=qf_lr,
#         )
#         self.vf_optimizer = optimizer_class(
#             self.vf.parameters(),
#             lr=vf_lr,
#         )

#         self.do_running_obs_norm = do_running_obs_norm
#         if do_running_obs_norm:
#             self.obs_mean = Variable(ptu.from_numpy(np.zeros((1, true_env_obs_dim))))
#             self.obs_std = Variable(ptu.from_numpy(np.ones((1, true_env_obs_dim))))
#             self.obs_sum = Variable(ptu.from_numpy(np.zeros((1, true_env_obs_dim))))
#             self.obs_sum_sq = Variable(ptu.from_numpy(np.zeros((1, true_env_obs_dim))))
#             self.obs_sum.requires_grad = False
#             self.obs_sum_sq.requires_grad = False
#             self.obs_count = 0.0
#             self.eps = 1e-2 * Variable(ptu.from_numpy(np.ones((1, true_env_obs_dim))))
#             self.eps.requires_grad = False


#     def get_exploration_policy(self, obs_task_params):
#         if self.wrap_absorbing: raise NotImplementedError('wrap absorbing')
#         if self.do_running_obs_norm:
#             return PostCondMLPPolicyWrapper(
#                 self.main_policy,
#                 obs_task_params,
#                 obs_mean=ptu.get_numpy(self.obs_mean)[0],
#                 obs_std=ptu.get_numpy(self.obs_std)[0]
#             )
#         return PostCondMLPPolicyWrapper(self.main_policy, obs_task_params)
    

#     def get_eval_policy(self, obs_task_params):
#         if self.wrap_absorbing: raise NotImplementedError('wrap absorbing')
#         if self.do_running_obs_norm:
#             return PostCondMLPPolicyWrapper(
#                 self.main_policy,
#                 obs_task_params,
#                 obs_mean=ptu.get_numpy(self.obs_mean)[0],
#                 obs_std=ptu.get_numpy(self.obs_std)[0]
#             )
#         # print(obs_task_params)
#         return PostCondMLPPolicyWrapper(self.main_policy, obs_task_params)
    

#     def _get_training_batch(self):
#         # get the batch for the tasks from policy buffer
#         policy_batch, task_identifiers = self.replay_buffer.sample_random_batch(
#             self.num_samples_per_task_per_batch,
#             self.num_tasks_per_batch
#         )
#         obs_task_params = np.array(list(map(lambda tid: self.env.task_id_to_obs_task_params(tid), task_identifiers)))
#         task_params_size = obs_task_params.shape[-1]
#         obs_task_params = np.repeat(obs_task_params, self.num_samples_per_task_per_batch, axis=-1)
#         obs_task_params = np.reshape(obs_task_params, (-1, task_params_size))

#         policy_obs = np.concatenate([d['observations'] for d in policy_batch], axis=0) # (N_tasks * batch_size) x Dim
#         policy_acts = np.concatenate([d['actions'] for d in policy_batch], axis=0) # (N_tasks * batch_size) x Dim
#         policy_terminals = np.concatenate([d['terminals'] for d in policy_batch], axis=0) # (N_tasks * batch_size) x Dim
#         policy_next_obs = np.concatenate([d['next_observations'] for d in policy_batch], axis=0) # (N_tasks * batch_size) x Dim
#         policy_rewards = np.concatenate([d['rewards'] for d in policy_batch], axis=0) # (N_tasks * batch_size) x Dim
#         # policy_absorbing = np.concatenate([d['absorbing'] for d in policy_batch], axis=0) # (N_tasks * batch_size) x Dim
#         policy_batch = dict(
#             observations=policy_obs,
#             actions=policy_acts,
#             terminals=policy_terminals,
#             next_observations=policy_next_obs,
#             rewards=policy_rewards
#             # absorbing=absorbing
#         )
#         return policy_batch, obs_task_params
    

#     def evaluate(self, epoch):
#         super().evaluate(epoch)
#         self.policy_optimizer.eval_statistics = None
    

#     def obtain_eval_samples(self, epoch, mode='meta_train'):
#         self.training_mode(False)

#         if mode == 'meta_train':
#             params_samples = self.train_task_params_sampler.sample_unique(self.num_tasks_per_eval)
#         else:
#             params_samples = self.test_task_params_sampler.sample_unique(self.num_tasks_per_eval)
#         all_eval_tasks_paths = []
#         for task_params, obs_task_params in params_samples:
#             cur_eval_task_paths = []
#             self.env.reset(task_params=task_params, obs_task_params=obs_task_params)
#             task_identifier = self.env.task_identifier

#             eval_policy = self.get_eval_policy(obs_task_params)
            
#             for _ in range(self.num_eval_trajs_per_task):
#                 cur_eval_path_builder = PathBuilder()
#                 observation = self.env.reset(task_params=task_params, obs_task_params=obs_task_params)
#                 terminal = False

#                 while (not terminal) and len(cur_eval_path_builder) < self.max_path_length:
#                     if isinstance(self.obs_space, Dict):
#                         if self.policy_uses_pixels:
#                             agent_obs = observation['pixels']
#                         else:
#                             agent_obs = observation['obs']
#                     else:
#                         agent_obs = observation
#                     action, agent_info = eval_policy.get_action(agent_obs)
                    
#                     next_ob, raw_reward, terminal, env_info = (self.env.step(action))
#                     if self.no_terminal:
#                         terminal = False
                    
#                     reward = raw_reward
#                     terminal = np.array([terminal])
#                     reward = np.array([reward])
#                     cur_eval_path_builder.add_all(
#                         observations=observation,
#                         actions=action,
#                         rewards=reward,
#                         next_observations=next_ob,
#                         terminals=terminal,
#                         agent_infos=agent_info,
#                         env_infos=env_info,
#                         task_identifiers=task_identifier
#                     )
#                     observation = next_ob

#                 if terminal and self.wrap_absorbing:
#                     raise NotImplementedError("I think they used 0 actions for this")
#                     cur_eval_path_builder.add_all(
#                         observations=next_ob,
#                         actions=action,
#                         rewards=reward,
#                         next_observations=next_ob,
#                         terminals=terminal,
#                         agent_infos=agent_info,
#                         env_infos=env_info,
#                         task_identifiers=task_identifier
#                     )
                
#                 if len(cur_eval_path_builder) > 0:
#                     cur_eval_task_paths.append(
#                         cur_eval_path_builder.get_all_stacked()
#                     )
#             all_eval_tasks_paths.extend(cur_eval_task_paths)
        
#         # flatten the list of lists
#         return all_eval_tasks_paths


#     def _do_training(self, epoch):
#         for _ in range(self.num_updates_per_train_call):
#             batch, obs_task_params = self._get_training_batch()
#             batch = np_to_pytorch_batch(batch)
#             obs_task_params = Variable(ptu.from_numpy(obs_task_params))

#             rewards = batch['rewards']
#             terminals = batch['terminals']
#             obs = batch['observations']
#             actions = batch['actions']
#             next_obs = batch['next_observations']

#             # normalize if needed and recompute values
#             if self.do_running_obs_norm:
#                 self.obs_sum += torch.sum(obs, dim=0, keepdim=True)
#                 self.obs_sum_sq += torch.sum(obs**2, dim=0, keepdim=True)
#                 self.obs_count += obs.size(0)
#                 self.obs_mean = self.obs_sum / self.obs_count
#                 self.obs_std = (self.obs_sum_sq / self.obs_count) - (self.obs_mean**2)
#                 self.obs_std = torch.max(self.obs_std, self.eps)
#                 # now normalize obs, and next_obs
#                 obs = (obs - self.obs_mean) / self.obs_std
#                 next_obs = (next_obs - self.obs_mean) / self.obs_std
#                 # print(self.obs_mean)
#                 # print(self.obs_std)

#             if self.policy_uses_task_params:
#                 obs = torch.cat([obs, obs_task_params], dim=-1)
#                 next_obs = torch.cat([next_obs, obs_task_params], dim=-1)

#             q1_pred = self.qf1(obs, actions)
#             q2_pred = self.qf2(obs, actions)
#             v_pred = self.vf(obs)
#             # Make sure policy accounts for squashing functions like tanh correctly!
#             policy_outputs = self.main_policy(obs, return_log_prob=True)
#             new_actions, policy_mean, policy_log_std, log_pi = policy_outputs[:4]

#             """
#             QF Loss
#             """
#             target_v_values = self.target_vf(next_obs)
#             q_target = rewards + (1. - terminals) * self.discount * target_v_values
#             qf1_loss = 0.5 * torch.mean((q1_pred - q_target.detach())**2)
#             qf2_loss = 0.5 * torch.mean((q2_pred - q_target.detach())**2)

#             """
#             VF Loss
#             """
#             q1_new_acts = self.qf1(obs, new_actions)
#             q2_new_acts = self.qf2(obs, new_actions)
#             q_new_actions = torch.min(q1_new_acts, q2_new_acts)
#             v_target = q_new_actions - log_pi
#             vf_loss = 0.5 * torch.mean((v_pred - v_target.detach())**2)

#             """
#             Policy Loss
#             """
#             policy_loss = torch.mean(log_pi - q_new_actions)
#             mean_reg_loss = self.policy_mean_reg_weight * (policy_mean**2).mean()
#             std_reg_loss = self.policy_std_reg_weight * (policy_log_std**2).mean()
#             # pre_tanh_value = policy_outputs[-1]
#             # pre_activation_reg_loss = self.policy_pre_activation_weight * (
#             #     (pre_tanh_value**2).sum(dim=1).mean()
#             # )
#             # policy_reg_loss = mean_reg_loss + std_reg_loss + pre_activation_reg_loss
#             policy_reg_loss = mean_reg_loss + std_reg_loss
#             policy_loss = policy_loss + policy_reg_loss

#             """
#             Update networks
#             """
#             self.qf1_optimizer.zero_grad()
#             qf1_loss.backward()
#             self.qf1_optimizer.step()

#             self.qf2_optimizer.zero_grad()
#             qf2_loss.backward()
#             self.qf2_optimizer.step()

#             self.vf_optimizer.zero_grad()
#             vf_loss.backward()
#             self.vf_optimizer.step()

#             self.policy_optimizer.zero_grad()
#             policy_loss.backward()
#             self.policy_optimizer.step()

#             self._update_target_network()

#             """
#             Save some statistics for eval
#             """
#             if self.eval_statistics is None:
#                 """
#                 Eval should set this to None.
#                 This way, these statistics are only computed for one batch.
#                 """
#                 self.eval_statistics = OrderedDict()
#                 self.eval_statistics['QF1 Loss'] = np.mean(ptu.get_numpy(qf1_loss))
#                 self.eval_statistics['QF2 Loss'] = np.mean(ptu.get_numpy(qf2_loss))
#                 self.eval_statistics['VF Loss'] = np.mean(ptu.get_numpy(vf_loss))
#                 self.eval_statistics['Policy Loss'] = np.mean(ptu.get_numpy(
#                     policy_loss
#                 ))
#                 self.eval_statistics.update(create_stats_ordered_dict(
#                     'Q1 Predictions',
#                     ptu.get_numpy(q1_pred),
#                 ))
#                 self.eval_statistics.update(create_stats_ordered_dict(
#                     'Q2 Predictions',
#                     ptu.get_numpy(q2_pred),
#                 ))
#                 self.eval_statistics.update(create_stats_ordered_dict(
#                     'V Predictions',
#                     ptu.get_numpy(v_pred),
#                 ))
#                 self.eval_statistics.update(create_stats_ordered_dict(
#                     'Log Pis',
#                     ptu.get_numpy(log_pi),
#                 ))
#                 self.eval_statistics.update(create_stats_ordered_dict(
#                     'Policy mu',
#                     ptu.get_numpy(policy_mean),
#                 ))
#                 self.eval_statistics.update(create_stats_ordered_dict(
#                     'Policy log std',
#                     ptu.get_numpy(policy_log_std),
#                 ))

#     @property
#     def networks(self):
#         return [
#             self.main_policy,
#             self.qf1,
#             self.qf2,
#             self.vf,
#             self.target_vf,
#         ]

#     def _update_target_network(self):
#         ptu.soft_update_from_to(self.vf, self.target_vf, self.soft_target_tau)

#     def get_epoch_snapshot(self, epoch):
#         snapshot = super().get_epoch_snapshot(epoch)
#         snapshot.update(
#             qf1=self.qf1,
#             qf2=self.qf2,
#             policy=self.main_policy,
#             vf=self.vf,
#             target_vf=self.target_vf,
#         )
#         return snapshot
