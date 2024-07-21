#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
#

import traceback
import socket
import json
def b2i(b):
    return int.from_bytes(b, 'little')
def i2b(i):
    return int(i).to_bytes(4,"little")
# head 0: image, 1: send_cameras, 2: don't send cameras
class RemoteRenderer():
    def __init__(self):
        self.socker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.begin_listen()
        self.conn = None
        self.addr = None
        self.can_send = False
        self.can_read = True
    def reset(self):
        self.conn.close()
        self.conn = None
    def begin_listen(self):
        try:

            host = "0.0.0.0"
            port = 12345
            self.socker.bind((host, port))
            self.socker.listen()
            self.socker.settimeout(0)
        except Exception as e:
            print(e)
            traceback.print_exc()
    def _get_a_renderer(self):
        if self.conn==None:
            try:
                self.conn, self.addr = self.socker.accept()
                print(f"\nConnected by {self.addr}")
                self.conn.settimeout(None)
                return True
            except Exception as inst:
                return False
        else:
            return True
    def read(self):
        has_con = self._get_a_renderer()
        if has_con:
            try:
                conn = self.conn
                head = conn.recv(4) # may stuck
                head = int.from_bytes(head,"little")
                ret_dic = {"status":1}
                if head==0:
                    self.can_read = True
                    ret_dic['image'] = self.read_image()#{"image":self.read_image()}
                elif head==1:
                    self.can_send = True
                    ret_dic['send'] = True
                elif head==2:
                    self.can_send = False
                    ret_dic['send'] = False
                elif head==3:
                    self.can_read = False
                return ret_dic
            except Exception as e:
                print(e)
                self.reset()
                return {"status":0}
        else:
            return {"status": 0}
    def read_image(self):
        # message = self.read()
        size = self.conn.recv(8)
        width,height = b2i(size[:4]),b2i(size[4:])
        message_length = width*height*3
        data_bytes = self.read_buffer(message_length)
        import numpy as np
        img_arr = np.frombuffer(data_bytes,dtype=np.uint8)
        img_arr = img_arr.reshape((width,height,3))
        return img_arr

    def read_buffer(self,messageLength):
        img_arr_bytes = b''
        while len(img_arr_bytes) < messageLength:
            chunk = self.conn.recv(messageLength - len(img_arr_bytes))
            if not chunk:
                break
            img_arr_bytes += chunk
        return img_arr_bytes

    def send_cameras(self,message_bytes):
        has_con = self._get_a_renderer()

        if has_con and self.can_send:
            try:
                print(self.can_send)
                conn = self.conn
                conn.sendall(i2b(0)) # 0: camera
                conn.sendall(len(message_bytes).to_bytes(4, 'little'))
                conn.sendall(message_bytes)
            except Exception as e:
                self.reset()
                print(e)

        else:
            pass

