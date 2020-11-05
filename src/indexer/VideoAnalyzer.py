import os, sys
import numpy as np
import cv2
from scipy.linalg import qr
import torch 
import torch.nn as nn
from torch.autograd import Variable
from torch.utils import data
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
from ffmpy import FFmpeg
import logging

imagenet_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

class ImageListDataset(data.Dataset):
    def __init__(self, image_list, transform=imagenet_transform):
        super().__init__()
        self.image_list = image_list
        self.transform = transform

    def __len__(self):
        return len(self.image_list)

    def __getitem__(self, index):
        x = self.image_list[index]
        return self.transform(x)

class VideoAnalyzer:
    def __init__(self, video, sampling_rate=10, n_keyframes=5):
        """
        video: cv2.VideoCapture object
        sampling_rate: ratio of total frames to samples
        n_keyframes: number of keyframes whose features 
                     we want to keep for search
        """
        self.video = video
        self.duration = self.frames = self.width = self.height = None
        _ = self.get_video_attributes(video)
        # check_sanity
        self.sampling_rate = sampling_rate
        self.n_samples = self.n_frames/sampling_rate
        self.n_keyframes = n_keyframes
        # print("init model")
        self.model = models.resnet18(pretrained=True)
        # print(type(self.model))
        # list of individual PIL Images 
        self.frame_images = [] 

        # np.array of indices where the key frames are
        self.keyframe_indices = [] 

        # np.array of features corresponding to those key frames 
        # should be a 512 x n_keyframes array
        self.keyframe_features = [] 

        self.analyze(video)

    def set_fsize(self, fsize):
        self.fsize = fsize

    def check_constraints(self):
        """
        check if video is too big/unsupported.
        return fail=1, set appropriate error
        """
        if self.fsize > 20:
            return False, 'file size larger than 20 MB not supported'
        #TODO : based on data statistics, how long it takes to process a video decide thresholds based on  w x h, frames
        return True, None

    def get_mean_feature(self):
        return self.keyframe_features.mean(axis=1)

    def analyze(self, video):
        # print("analyzing video")
        self.frame_images = self.extract_frames(video)
        feature_matrix = self.extract_features(self.frame_images)
        self.keyframe_indices = self.find_keyframes(feature_matrix)
        self.keyframe_features = feature_matrix[:,self.keyframe_indices]
        # print("analysed video")

    def get_video_attributes(self, v):
        # print("getting video attributes")
        if self.duration is not None:
            return {'duration' : self.duration,
                    'n_frames' : self.n_frames,
                    'width'  : self.width,
                    'height' : self.height}
        width  = v.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = v.get(cv2.CAP_PROP_FRAME_HEIGHT)
        # duration in seconds
        v.set(cv2.CAP_PROP_POS_AVI_RATIO,1)
        fps = v.get(cv2.CAP_PROP_FPS)
        frame_count = int(v.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = frame_count/fps
        self.n_frames = frame_count
        self.width = width
        self.height = height
        v.set(cv2.CAP_PROP_POS_AVI_RATIO,0)
        # print("got video attributes")
        return {'duration' : self.duration,
                'n_frames' : self.n_frames,
                'width'  : self.width,
                'height' : self.height}	

    def extract_frames(self, v):
        # print("extracting frames")
        images = []
        for i in range(self.n_frames):
            success, image = v.read()
            if image is None:
                continue
            else:
                if i % self.sampling_rate == 0:
                   images.append(Image.fromarray(image))
        # print("extracted frames")
        return images

    def extract_features(self, images): 
        try:
            # print('extracting features')
            # print("init dataset")
            dset = ImageListDataset(images)
            # print("done")
            # print("init dataloader")
            dloader = data.DataLoader(dset, batch_size=len(images), num_workers=1)
            # dloader = data.DataLoader(dset, batch_size=1, num_workers=1)
            # print(len(images))
            # print("done")
            # print("do embedding")
            embedding = torch.zeros(512, len(images))
            def hook(m, i, o):
                feature_data = o.data.reshape((512, len(images)))
                # feature_data = o.data.reshape((512, 1))
                embedding.copy_(feature_data)
            # print("get feature layer")
            feature_layer = self.model._modules.get('avgpool')
            # print("feature layer:", feature_layer)
            # print("done")
            # print("register hook")
            h = feature_layer.register_forward_hook(hook)
            # print("done")
            # print("feature layer:", feature_layer)
            # print("h:", h)
            # print("calling model.eval()")
            self.model.eval()
            # print("done")
            print("iterate through dataloader")
            self.model(next(iter(dloader)))
            print("done")
            h.remove()
            # print("extracted features")
            return embedding.numpy()
        except Exception:
            print(logging.traceback.format_exc())

    def find_keyframes(self, feature_matrix):
        # print("finding keyframes")
        Q, R, P = qr(feature_matrix, pivoting=True,overwrite_a=False)
        idx = P[:self.n_keyframes]
        # print("found keyframes")
        return idx

def compress_video(fname):
    newname = "/tmp/compressed.mp4"
    FNULL = open(os.devnull, 'w')
    ff = FFmpeg(
        global_options='-y',
        inputs={fname: None},
        outputs={newname: '-vcodec libx265 -crf 28'}
    )
    print(ff.cmd)
    ff.run(stdout=FNULL, stderr=FNULL)
    os.remove(fname)
    return newname

if __name__ == "__main__":
    if len(sys.argv) > 1:
        vid = cv2.VideoCapture(sys.argv[1])
    else:
        DATA_DIR = os.environ.get('DATA_DIR','.')
        vid = cv2.VideoCapture(DATA_DIR+'/1.mp4')
    analyzer = VideoAnalyzer(vid)
