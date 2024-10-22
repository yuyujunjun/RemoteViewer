#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

import torch
import traceback
import socket
import json
import pickle
from m_scripts.camera_utils import GS_Cam
import zlib
def b2i(b):
    return int.from_bytes(b, 'little')
def i2b(i):
    return int(i).to_bytes(4,"little")
# Peer: head 0: image, 1: send_cameras, 2: don't send cameras
# head 0: camera
class RemoteViewer():
    def __init__(self,host,port):
        self.host = host
        self.port = port
        self.recieve_camera = False
        self.contiunous_mode = False
        self.peer_status = {"image":1,"send":2,"dont send":3,"dont receive":4}
        self.connect_success = False
    def reset_connect(self):
        self.connect_success = False
        self.socker.close()
    def send_current_state(self):
        status = self.peer_status["send"] if self.recieve_camera else self.peer_status["dont send"]
        self.socker.sendall(i2b(status))
    def i_dont_send_more_data(self):
        self.socker.sendall(i2b(self.peer_status["dont receive"]))
    def require_camera_from_remote(self, status):
        if self.recieve_camera!=status:
            self.recieve_camera = status
            if self.try_connect():
                self.send_current_state()

    def try_connect(self):
        if self.connect_success == False:
            print("try_connect")
            try:
                self.socker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socker.connect((self.host, self.port))
                self.send_current_state() # synchronize camera state first
                self.connect_success=True
                return True
            except Exception as e:
                self.connect_success = False
                return False
        else:
            return True
    def close(self):
        self.socker.close()

    def read(self):
        has_viewer = self.try_connect()
        if has_viewer:
            try:
                print("read")
                head = self.socker.recv(4)
                head = b2i(head)
                ret_dict = {"status":1}
                if head == 0:
                     ret_dict["camera"] = self._read_cameras()
                return ret_dict
            except Exception as e:
                print(e)
                # assume the connection is broken
                self.reset_connect()
                return {"status":0}
        return {"status":0}

    def send_images(self,images:list,single=False): #W
        has_viewer = self.try_connect()
        if has_viewer:
            try:
                if isinstance(images,list)==False:
                    images = [images]
                # print("send_images")
                import numpy as np
                num = len(images)
                self.socker.sendall(i2b(self.peer_status["image"])+i2b(num))
                for i in range(num):
                    image = images[i]
                    image = np.array(image)
                    img_str = pickle.dumps(image)
                    image_bytes = zlib.compress(img_str,zlib.Z_BEST_COMPRESSION)
                    length = len(image_bytes)
                    # image_bytes = image.astype(np.uint8).tobytes()
                    width,height = image.shape[0].to_bytes(4,"little"),image.shape[1].to_bytes(4,"little")
                    self.socker.sendall(i2b(length)+width+height)
                    self.socker.sendall(image_bytes)
                if single:
                    self.i_dont_send_more_data()
                # print("send done")
            except Exception as e:
                # assume the connection is broken
                self.reset_connect()
    def _read_cameras(self):
        message_length = self.socker.recv(4)
        message_length = b2i(message_length)
        messages = self._read_buffer(message_length)
        fovx,znear,zfar,world_view_transform,full_proj_transform = pickle.loads(messages)
        world_view_transform = world_view_transform.to("cuda")
        full_proj_transform = full_proj_transform.to("cuda")
        return GS_Cam(0,0,fovx,fovx,znear,zfar,world_view_transform,full_proj_transform)

    def _read_buffer(self, messageLength):
        img_arr_bytes = b''
        while len(img_arr_bytes) < messageLength:
            chunk = self.socker.recv(messageLength - len(img_arr_bytes))
            if not chunk:
                break
            img_arr_bytes += chunk
        return img_arr_bytes

