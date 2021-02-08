# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Inferer for DeepSpeech2 model."""

import sys
import argparse
import functools
import paddle.fluid as fluid
from data_utils.data import DataGenerator
from data_utils.dataset import create_dataloader
from model_utils.model import DeepSpeech2Model
from model_utils.model_check import check_cuda, check_version
from utils.error_rate import wer, cer
from utils.utility import add_arguments, print_arguments

parser = argparse.ArgumentParser(description=__doc__)
add_arg = functools.partial(add_arguments, argparser=parser)
# yapf: disable
add_arg('num_samples',      int,    10,     "# of samples to infer.")
add_arg('beam_size',        int,    500,    "Beam search width.")
add_arg('num_proc_bsearch', int,    8,      "# of CPUs for beam search.")
add_arg('num_conv_layers',  int,    2,      "# of convolution layers.")
add_arg('num_rnn_layers',   int,    3,      "# of recurrent layers.")
add_arg('rnn_layer_size',   int,    2048,   "# of recurrent cells per layer.")
add_arg('alpha',            float,  2.5,    "Coef of LM for beam search.")
add_arg('beta',             float,  0.3,    "Coef of WC for beam search.")
add_arg('cutoff_prob',      float,  1.0,    "Cutoff probability for pruning.")
add_arg('cutoff_top_n',     int,    40,     "Cutoff number for pruning.")
add_arg('use_gru',          bool,   False,  "Use GRUs instead of simple RNNs.")
add_arg('use_gpu',          bool,   True,   "Use GPU or not.")
add_arg('share_rnn_weights',bool,   True,   "Share input-hidden weights across "
                                            "bi-directional RNNs. Not for GRU.")
add_arg('infer_manifest',   str,
        'data/librispeech/manifest.dev-clean',
        "Filepath of manifest to infer.")
add_arg('mean_std_path',    str,
        'data/librispeech/mean_std.npz',
        "Filepath of normalizer's mean & std.")
add_arg('vocab_path',       str,
        'data/librispeech/vocab.txt',
        "Filepath of vocabulary.")
add_arg('lang_model_path',  str,
        'models/lm/common_crawl_00.prune01111.trie.klm',
        "Filepath for language model.")
add_arg('model_path',       str,
        './checkpoints/libri/step_final',
        "If None, the training starts from scratch, "
        "otherwise, it resumes from the pre-trained model.")
add_arg('decoding_method',  str,
        'ctc_beam_search',
        "Decoding method. Options: ctc_beam_search, ctc_greedy",
        choices = ['ctc_beam_search', 'ctc_greedy'])
add_arg('error_rate_type',  str,
        'wer',
        "Error rate type for evaluation.",
        choices=['wer', 'cer'])
add_arg('specgram_type',    str,
        'linear',
        "Audio feature type. Options: linear, mfcc.",
        choices=['linear', 'mfcc'])
# yapf: disable
args = parser.parse_args()


def infer():
    """Inference for DeepSpeech2."""

    # check if set use_gpu=True in paddlepaddle cpu version
    check_cuda(args.use_gpu)
    # check if paddlepaddle version is satisfied
    check_version()

    # data_generator = DataGenerator(
    #     vocab_filepath=args.vocab_path,
    #     mean_std_filepath=args.mean_std_path,
    #     augmentation_config='{}',
    #     specgram_type=args.specgram_type,
    #     keep_transcription_text=True,
    #     place = place,
    #     is_training = False)
    # batch_reader = data_generator.batch_reader_creator(
    #     manifest_path=args.infer_manifest,
    #     batch_size=args.num_samples,
    #     sortagrad=False,
    #     shuffle_method=None)

    batch_reader = create_dataloader(
            manifest_path=args.infer_manifest,
            vocab_filepath=args.vocab_path,
            mean_std_filepath=args.mean_std_path,
            augmentation_config='{}',
            max_duration=float('inf'),
            min_duration=0.0,
            stride_ms=10.0,
            window_ms=20.0,
            max_freq=None,
            specgram_type=args.specgram_type,
            use_dB_normalization=True,
            random_seed=0,
            keep_transcription_text=False,
            is_training=False,
            batch_size=args.num_samples,
            sortagrad=False,
            shuffle_method=None)

    #for audio, text, audio_len, text_len in batch_reader:
    #    print(audio.shape)
    #    print(text.shape)
    #    print(audio_len)
    #    print(text_len)
    #    break

    reader = batch_reader()
    infer_data = reader.next()
    print(infer_data)

    from model_utils.network2 import DeepSpeech2
    feat_dim=161
    model = DeepSpeech2(
        feat_size=feat_dim,
        dict_size=batch_reader.dataset.vocab_size,
        num_conv_layers=args.num_conv_layers,
        num_rnn_layers=args.num_rnn_layers,
        #rnn_size=1024,
        use_gru=args.use_gru,
        share_rnn_weights=args.share_rnn_weights,
    )

    output = model(*infer_data)
    print(output)

    # ds2_model = DeepSpeech2Model(
    #     vocab_size=data_generator.vocab_size,
    #     num_conv_layers=args.num_conv_layers,
    #     num_rnn_layers=args.num_rnn_layers,
    #     rnn_layer_size=args.rnn_layer_size,
    #     use_gru=args.use_gru,
    #     share_rnn_weights=args.share_rnn_weights,
    #     place=place,
    #     init_from_pretrained_model=args.model_path)

    # # decoders only accept string encoded in utf-8
    # vocab_list = [chars for chars in data_generator.vocab_list]

    # if args.decoding_method == "ctc_greedy":
    #     ds2_model.logger.info("start inference ...")
    #     probs_split = ds2_model.infer_batch_probs(
    #         infer_data=infer_data,
    #         feeding_dict=data_generator.feeding)

    #     result_transcripts = ds2_model.decode_batch_greedy(
    #         probs_split=probs_split,
    #         vocab_list=vocab_list)
    # else:
    #     ds2_model.init_ext_scorer(args.alpha, args.beta, args.lang_model_path,
    #                               vocab_list)
    #     ds2_model.logger.info("start inference ...")
    #     probs_split= ds2_model.infer_batch_probs(
    #         infer_data=infer_data,
    #         feeding_dict=data_generator.feeding)

    #     result_transcripts= ds2_model.decode_batch_beam_search(
    #         probs_split=probs_split,
    #         beam_alpha=args.alpha,
    #         beam_beta=args.beta,
    #         beam_size=args.beam_size,
    #         cutoff_prob=args.cutoff_prob,
    #         cutoff_top_n=args.cutoff_top_n,
    #         vocab_list=vocab_list,
    #         num_processes=args.num_proc_bsearch)

    # error_rate_func = cer if args.error_rate_type == 'cer' else wer
    # target_transcripts = infer_data[1]
    # for target, result in zip(target_transcripts, result_transcripts):
    #     print("\nTarget Transcription: %s\nOutput Transcription: %s" %
    #           (target, result))
    #     print("Current error rate [%s] = %f" %
    #           (args.error_rate_type, error_rate_func(target, result)))

    # ds2_model.logger.info("finish inference")

def main():
    print_arguments(args)
    infer()


if __name__ == '__main__':
    main()
