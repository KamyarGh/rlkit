meta_data:
  script_path: /h/kamyar/oorl_rlkit/run_scripts/train_np_bc.py
  exp_dirs: /scratch/gobi2/kamyar/oorl_rlkit/output
  exp_name: first_try_few_shot_np_bc
  description: searching over the SAC hyperparameters
  use_gpu: false
  num_workers: 128
  cpu_range: [0,159]
  num_cpu_per_worker: 1
# -----------------------------------------------------------------------------
variables:
  algo_params:
    policy_net_size: [100, 256]
    policy_num_layers: [3, 4]

    num_tasks_used_per_update: [5]
    test_batch_size_per_task: [256, 512]
  
    np_params:
      z_dim: [20, 40, 60, 80]

      traj_enc_params:
          timestep_enc_params:
            # input_size must be inferred based on env
              [
                {hidden_sizes: [50], output_size: 50},
                {hidden_sizes: [100], output_size: 100}
              ]

  seed: [9783, 5914]
  # seed: [9783]
  # seed: [9783, 5914, 4865, 2135, 2349]

# -----------------------------------------------------------------------------
constants:
  expert_name: normalized_basic_few_shot_fetch_larger_object_range_expert_50_10_10
  expert_seed_run_idx: 0

  algo_params:
    num_epochs: 1011
    num_rollouts_per_epoch: 1
    min_rollouts_before_training: 0
    max_path_length: 65

    replay_buffer_size_per_task: 100
    no_terminal: false

    num_policy_updates_per_epoch: 4000
    num_context_trajs_for_training: 3

    num_tasks_per_eval: 10
    num_diff_context_per_eval_task: 2
    num_context_trajs_for_eval_task: 3
    num_eval_trajs_per_post_sample: 2

    num_context_trajs_for_exploration: 3

    # policy params
    policy_uses_pixels: false
    use_layer_norm: false

    policy_lr: 0.0003
    encoder_lr: 0.0003

    np_params:
      # z_dim: 20

      traj_enc_params:
      #   timestep_enc_params:
      #     # input_size must be inferred based on env
      #     hidden_sizes: [50]
      #     output_size: 50

        traj_enc_params:
          # input_size must be inferred
          hidden_sizes: [100]
          output_size: 100
      
      r2z_map_params:
        trunk_params:
          # input_size must be inferred
          hidden_sizes: []
          output_size: 100
        split_heads_params:
          # input_size must be inferred
          hidden_sizes: [100]
          # output_size must be inferred
      
      np_enc_params:
        agg_type: 'sum'
        

    save_replay_buffer: true
    save_algorithm: true
    render: false

    freq_saving: 25
    
  env_specs:
    base_env_name: 'scaled_basic_few_shot_fetch_env'
    normalized: false
    need_pixels: false