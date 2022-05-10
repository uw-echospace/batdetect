from __future__ import print_function
import chunk
from curses import raw
import numpy as np
import os
import fnmatch
import time
import sys

import write_op as wo
import cpu_detection as detector
import mywavfile

import matplotlib.pyplot as plt
from matplotlib import patches, text, patheffects

def get_audio_files(ip_dir):
    matches = []
    for root, dirnames, filenames in os.walk(ip_dir):
        for filename in filenames:
            if filename.lower().endswith('.wav'):
                matches.append(os.path.join(root, filename))
    return matches


def read_audio(file_name, do_time_expansion, chunk_size, win_size):
    # try to read in audio file
    try:
        samp_rate_orig, audio = mywavfile.read(file_name)
    except:
        print('  Error reading file')
        return True, None, None, None, None

    # convert to mono if stereo
    if len(audio.shape) == 2:
        print('  Warning: stereo file. Just taking left channel.')
        audio = audio[:, 0]
    file_dur = audio.shape[0] / float(samp_rate_orig)
    print('  dur', round(file_dur,3), '(secs) , fs', samp_rate_orig)

    # original model is trained on time expanded data
    samp_rate = samp_rate_orig
    if do_time_expansion:
        samp_rate = int(samp_rate_orig/10.0)
        file_dur *= 10

    # pad with zeros so we can go right to the end
    multiplier = np.ceil(file_dur/float(chunk_size-win_size))
    diff = multiplier*(chunk_size-win_size) - file_dur + win_size
    audio_pad = np.hstack((audio, np.zeros(int(diff*samp_rate))))

    return False, audio_pad, file_dur, samp_rate, samp_rate_orig


def run_model(det, audio, file_dur, samp_rate, detection_thresh, max_num_calls=0):
    """This runs the bat call detector.
    """
    # results will be stored here
    det_time_file = np.zeros(0)
    det_prob_file = np.zeros(0)

    #full_hspec = np.zeros((det.max_freq-det.min_freq, 0))
    #full_spec = np.zeros(((det.max_freq-det.min_freq)/2, 0))

    # files can be long so we split each up into separate (overlapping) chunks
    st_positions = np.arange(0, file_dur, det.chunk_size-det.win_size)
    for chunk_id, st_position in enumerate(st_positions):

        # take a chunk of the audio
        # should already be zero padded at the end so its the correct size
        st_pos = int(st_position*samp_rate)
        en_pos = int(st_pos + det.chunk_size*samp_rate)
        audio_chunk = audio[st_pos:en_pos]
        chunk_duration = audio_chunk.shape[0] / float(samp_rate)

        # create spectrogram
        hspec, spec = det.create_spec(audio_chunk, samp_rate)

        # run detector
        det_loc, prob_det = det.run_detection(spec, chunk_duration, detection_thresh,
                                              low_res=True)

        #full_hspec = np.hstack((full_hspec, hspec))
        #full_spec = np.hstack((full_spec, spec))
        det_time_file = np.hstack((det_time_file, det_loc + st_position))
        det_prob_file = np.hstack((det_prob_file, prob_det))

    # undo the effects of time expansion for detector
    if do_time_expansion:
        det_time_file /= 10.0

    return det_time_file, det_prob_file

# Plots all figures from figure 1.
def plot_calls(audio, det_time):

    # Store duration of audio in seconds for future plotting
    orig_audio_length1 = len(audio)/float(samp_rate_orig)

    # Create spectrograms raw and processed from full audio 
    # Previous calls only input chunks of the audio
    # For future, try concatenating each chunk's spectrogram to plot off of the main code
    raw_spec, proc_spec = det.create_spec(audio, samp_rate)

    # Initialize subplots 4 rows and 1 column
    fig, axes = plt.subplots(4, 1, figsize=(10, 12))
    
    # Plot the raw audio first with samples from 0 to duration of audio 
    # according to the original sample rate (before time expansion)
    ax = axes[0]
    t = np.arange(0, len(audio))/float(samp_rate_orig)
    sig = audio/1000 # normalize amplitude values for a cleaner look
    ax.plot(t, sig) 
    ax.set_ylabel("Amplitude (*10^3)")
    ax.set_xlabel("Time (s)")
    ax.set(title="Raw Audio")

    # Plot the raw spectrogram generated from the full audio
    # Get time values from 0 to duration of audio with samples according to spectrogram frames
    ax = axes[1]
    raw_time_step = orig_audio_length1/float(raw_spec.shape[1])
    raw_times = np.arange(0, orig_audio_length1, raw_time_step)
    raw_freqs = np.arange(det.min_freq, det.max_freq, 1)
    ax.pcolormesh(raw_times, raw_freqs, np.flipud(raw_spec)) # Spectrogram is flipped in spectrogram.py so we flip again
    ax.set_ylabel("Frequency (kHz)")
    ax.set_xlabel("Time (s)")
    ax.set(title="Raw Spectrogram")

    # Plot the processed spectrogram generated from the full audio
    # Get time values from 0 to duration of audio with samples according to spectrogram frames
    ax = axes[2]
    proc_time_step = orig_audio_length1/float(proc_spec.shape[1])
    proc_times = np.arange(0, orig_audio_length1, proc_time_step)
    proc_freqs = np.arange(det.min_freq, det.max_freq, 2)
    ax.pcolormesh(proc_times, proc_freqs, np.flipud(proc_spec)) # Spectrogram is flipped in spectrogram.py so we flip again
    ax.set_ylabel("Frequency (kHz)")
    ax.set_xlabel("Time (s)")
    ax.set(title="Noise-Reduced Spectrogram")

    # Plot the raw spectrogram generated from the full audio
    # Get time values from 0 to duration of audio with samples according to spectrogram frames
    ax = axes[3]
    ax.pcolormesh(raw_times, raw_freqs, np.flipud(raw_spec))
    ax.set_ylabel("Frequency (kHz)")
    ax.set_xlabel("Time (s)")
    ax.set(title="Detections Overlayed")
    # Draw a boundary over each x-coordinate calculated by CNN model. 
    # Use 2 times the fft window length as the width of our boundary.
    # x-coordinate is approximately at the start of each call
    for i in det_time:
        ax.add_patch(patches.Rectangle((i-(det.slice_scale/2), 0), (3*det.slice_scale/2), 
        raw_spec.shape[0], fill=False, edgecolor='yellow', lw=2))

    # Organize all of our plots so no overlapping and show plot for each file
    # Each window corresponds to a file in our data folder, closing a window moves to next file
    # Closing the last window will mark the end of the program
    plt.tight_layout()
    plt.show()
    



if __name__ == "__main__":

    # params
    detection_thresh = 0.68        # Current range: [0.43, 0.68]; make this smaller if you want more calls
    do_time_expansion = True       # if audio is already time expanded set this to False
    save_individual_results = True # if True will create an output for each file
    save_summary_result = True     # if True will create a single csv file with all results

    # load data
    data_dir = 'short_ub_calls'                                   # this is the path to your audio files
    op_ann_dir = 'short_ub_results'                              # this where your results will be saved
    op_ann_dir_ind = os.path.join(op_ann_dir, 'individual_results')  # this where individual results will be saved
    op_file_name_total = os.path.join(op_ann_dir, 'results.csv')
    if not os.path.isdir(op_ann_dir):
        os.makedirs(op_ann_dir)
    if save_individual_results and not os.path.isdir(op_ann_dir_ind):
        os.makedirs(op_ann_dir_ind)

    # read audio files
    audio_files = get_audio_files(data_dir)

    print('Processing        ', len(audio_files), 'files')
    print('Input directory   ', data_dir)
    print('Results directory ', op_ann_dir, '\n')


    # load and create the detector    
    det_model_file = 'models/detector.npy'
    # The parameters are in models/detector_params.json
    det_params_file = det_model_file[:-4] + '_params.json'
    # Method CPUDetector is in cpu_detection.py
    det = detector.CPUDetector(det_model_file, det_params_file)

    # loop through audio files
    results = []
    for file_cnt, file_name in enumerate(audio_files):

        file_name_basename = file_name[len(data_dir):]
        print('\n', file_cnt+1, 'of', len(audio_files), '\t', file_name_basename)

        # read audio file - skip file if can't read it
        read_fail, audio, file_dur, samp_rate, samp_rate_orig = read_audio(file_name,
                                do_time_expansion, det.chunk_size, det.win_size)
        if read_fail:
            continue

        # run detector
        tic = time.time()
        det_time, det_prob  = run_model(det, audio, file_dur, samp_rate,
                                        detection_thresh)
        toc = time.time()

        print('  detection time', round(toc-tic, 3), '(secs)')
        num_calls = len(det_time)
        print('  ' + str(num_calls) + ' calls found')

        # Calling our method here to plot a figure for each file in the directory
        plot_calls(audio, det_time)

        # save results
        if save_individual_results:
            # save to AudioTagger format
            f_name_fmt = file_name_basename.replace('/', '_').replace('\\', '_')[:-4]
            op_file_name = os.path.join(op_ann_dir_ind, f_name_fmt) + '-sceneRect.csv'
            wo.create_audio_tagger_op(file_name_basename, op_file_name, det_time,
                                      det_prob, samp_rate_orig, class_name='bat')

        # save as dictionary
        if num_calls > 0:
            res = {'filename':file_name_basename, 'time':det_time, 'prob':det_prob}
            results.append(res)

    # save results for all files to large csv
    if save_summary_result and (len(results) > 0):
        print('\nsaving results to', op_file_name_total)
        wo.save_to_txt(op_file_name_total, results)
    else:
        print('no detections to save')
