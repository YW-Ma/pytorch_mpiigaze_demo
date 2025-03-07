import argparse
import logging
import pathlib
import warnings

import torch
from omegaconf import DictConfig, OmegaConf

from demo import Demo
from utils import (check_path_all, download_dlib_pretrained_model,
                    download_ethxgaze_model, download_mpiifacegaze_model,
                    download_mpiigaze_model, expanduser_all,
                    generate_dummy_camera_params)
from threading import Thread, Lock
from time import sleep, ctime
import numpy as np

logger = logging.getLogger(__name__)
lock = Lock() 

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config',
        type=str,
        help='Config file. When using a config file, all the other '
        'commandline arguments are ignored. '
        'See https://github.com/hysts/pytorch_mpiigaze_demo/ptgaze/data/configs/eth-xgaze.yaml'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['mpiigaze', 'mpiifacegaze', 'eth-xgaze'],
        help='With \'mpiigaze\', MPIIGaze model will be used. '
        'With \'mpiifacegaze\', MPIIFaceGaze model will be used. '
        'With \'eth-xgaze\', ETH-XGaze model will be used.')
    parser.add_argument(
        '--face-detector',
        type=str,
        default='mediapipe',
        choices=[
            'dlib', 'face_alignment_dlib', 'face_alignment_sfd', 'mediapipe'
        ],
        help='The method used to detect faces and find face landmarks '
        '(default: \'mediapipe\')')
    parser.add_argument('--device',
                        type=str,
                        choices=['cpu', 'cuda'],
                        help='Device used for model inference.')
    parser.add_argument('--image',
                        type=str,
                        help='Path to an input image file.')
    parser.add_argument('--video',
                        type=str,
                        help='Path to an input video file.')
    parser.add_argument(
        '--camera',
        type=str,
        help='Camera calibration file. '
        'See https://github.com/hysts/pytorch_mpiigaze_demo/ptgaze/data/calib/sample_params.yaml'
    )
    parser.add_argument(
        '--output-dir',
        '-o',
        type=str,
        help='If specified, the overlaid video will be saved to this directory.'
    )
    parser.add_argument('--ext',
                        '-e',
                        type=str,
                        choices=['avi', 'mp4'],
                        help='Output video file extension.')
    parser.add_argument(
        '--no-screen',
        action='store_true',
        help='If specified, the video is not displayed on screen, and saved '
        'to the output directory.')
    parser.add_argument('--debug', action='store_true')
    return parser.parse_args()


def load_mode_config(args: argparse.Namespace) -> DictConfig:
    package_root = pathlib.Path(__file__).parent.resolve()
    if args.mode == 'mpiigaze':
        path = package_root / 'data/configs/mpiigaze.yaml'
    elif args.mode == 'mpiifacegaze':
        path = package_root / 'data/configs/mpiifacegaze.yaml'
    elif args.mode == 'eth-xgaze':
        path = package_root / 'data/configs/eth-xgaze.yaml'
    else:
        raise ValueError
    config = OmegaConf.load(path)
    config.PACKAGE_ROOT = package_root.as_posix()

    if args.face_detector:
        config.face_detector.mode = args.face_detector
    if args.device:
        config.device = args.device
    if config.device == 'cuda' and not torch.cuda.is_available():
        config.device = 'cpu'
        warnings.warn('Run on CPU because CUDA is not available.')
    if args.image and args.video:
        raise ValueError('Only one of --image or --video can be specified.')
    if args.image:
        config.demo.image_path = args.image
        config.demo.use_camera = False
    if args.video:
        config.demo.video_path = args.video
        config.demo.use_camera = False
    if args.camera:
        config.gaze_estimator.camera_params = args.camera
    elif args.image or args.video:
        config.gaze_estimator.use_dummy_camera_params = True
    if args.output_dir:
        config.demo.output_dir = args.output_dir
    if args.ext:
        config.demo.output_file_extension = args.ext
    if args.no_screen:
        config.demo.display_on_screen = False
        if not config.demo.output_dir:
            config.demo.output_dir = 'outputs'

    return config


def main():
    args = parse_args()
    t1 = Thread(target=work1, args=(args,))
    t1.start()

    t2 = Thread(target=work2, args=())
    t2.start()


def work1(args):
    global demo
    lock.acquire()
    if args.debug:
        logging.getLogger('ptgaze').setLevel(logging.DEBUG)

    if args.config:
        config = OmegaConf.load(args.config)
    elif args.mode:
        config = load_mode_config(args)
    else:
        raise ValueError(
            'You need to specify one of \'--mode\' or \'--config\'.')
    expanduser_all(config)
    if config.gaze_estimator.use_dummy_camera_params:
        generate_dummy_camera_params(config)

    OmegaConf.set_readonly(config, True)
    logger.info(OmegaConf.to_yaml(config))

    if config.face_detector.mode == 'dlib':
        download_dlib_pretrained_model()
    if args.mode:
        if config.mode == 'MPIIGaze':
            download_mpiigaze_model()
        elif config.mode == 'MPIIFaceGaze':
            download_mpiifacegaze_model()
        elif config.mode == 'ETH-XGaze':
            download_ethxgaze_model()

    check_path_all(config)
    demo = Demo(config)
    lock.release()
    demo.run()

import pyautogui
def work2():
    screenWidth, screenHeight = pyautogui.size() # Get the size of the primary monitor.
    currentMouseX, currentMouseY = pyautogui.position()
    sleep(1) # make sure work1 can get the lock
    lock.acquire()
    global demo
    CALIBRATION_INTERVAL = 3 # change this interval
    CURSOR_INTERVAL = 1
    lock.release()

    # first four results is used to calibration
    x_right, x_left, y_up, y_down = 0, 0, 0, 0 
    # min     max     min     max

    iteration = 0
    while True:
        x = 0
        y = 0
        for res in demo.gaze_estimator.results:
            x += res[0]
            y += res[1]
        array = np.array(demo.gaze_estimator.results)
        
        # preprocesing: np.abs(data - np.mean(data, axis=0)) > np.std(data, axis=0) and only keep the all true ones
        x /= -len(demo.gaze_estimator.results) # change sign (right should be larger than left)
        y /= len(demo.gaze_estimator.results)
        

        # calibration
        if iteration == 0:
            logger.info("------------------- Look Upper-left -------------------")
            sleep(CALIBRATION_INTERVAL)
            iteration += 1
            continue
        if iteration == 1: # upper-left
            x_left += x
            y_up += y
            logger.info("------------------- Then Look Upper-right -------------------")
            sleep(CALIBRATION_INTERVAL)
            iteration += 1
            continue
        elif iteration == 2: # upper-right
            x_right += x
            y_up += y
            logger.info("------------------- Then Look lower-right -------------------")
            sleep(CALIBRATION_INTERVAL)
            iteration += 1
            continue
        elif iteration == 3: # lower-right
            x_right += x
            y_down += y
            logger.info("------------------- Then Look lower-left -------------------")
            sleep(CALIBRATION_INTERVAL)
            iteration += 1
            continue
        elif iteration == 4: # lower-left
            x_left += x
            y_down += y
            logger.info("-------------------------------------- Finished --------------------------------------")
            sleep(CALIBRATION_INTERVAL)
            iteration += 1
            continue
        elif iteration == 5:
            x_right, x_left, y_up, y_down = x_right / 2, x_left / 2, y_up / 2, y_down / 2
            logger.info("\nFinished calibration: \n x_right {}, \n x_left {}, \n y_up {}, \n y_down {}".format(x_right, x_left, y_up, y_down))


        # after calibration, shrink the interval:
        
        # scale x and y
        x = (x - x_left) / (x_right - x_left) * (screenWidth)
        y = (y - y_up) / (y_down - y_up) * (screenHeight)
        logger.info("\n x:{}   y: {}".format(x, y))
        if x <= 0:
            x = 1
        if x >= screenWidth:
            x = screenWidth - 1
        if y <= 0:
            y = 1
        if y >= screenHeight:
            y = screenHeight - 1

        pyautogui.moveTo(x, y) # x, y  positive number

        sleep(CURSOR_INTERVAL)
        iteration += 1



args = parse_args()
t1 = Thread(target=work1, args=(args,))
t1.start()

t2 = Thread(target=work2, args=())
t2.start()