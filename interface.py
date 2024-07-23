import numpy as np
from array import array
from imgui.integrations.glfw import GlfwRenderer
from math import sin, pi
from random import random
from time import time
import OpenGL.GL as gl
import glfw
import imgui
import sys
import glm
from RemoteRenderer import RemoteRenderer
import pickle
import torch

# from controller: input->model-view matrix
# from application: model-view matrix
def normalize_vecs(vectors: torch.Tensor) -> torch.Tensor:
    '''
    From EG3D
    '''
    return vectors / (torch.norm(vectors, dim=-1, keepdim=True))
def create_cam2world_matrix(forward_vector, origin):
    """
    Takes in the direction the camera is pointing and the camera origin and returns a cam2world matrix.
    Works on batches of forward_vectors, origins. Assumes y-axis is up and that there is no camera roll.
    """


    forward_vector = normalize_vecs(forward_vector)
    up_vector = torch.tensor([0, 1, 0], dtype=torch.float,
                             device=origin.device).expand_as(forward_vector)

    right_vector = - \
        normalize_vecs(torch.cross(up_vector, forward_vector, dim=-1))
    up_vector = normalize_vecs(torch.cross(
        forward_vector, right_vector, dim=-1))

    rotation_matrix = torch.eye(4, device=origin.device).unsqueeze(
        0).repeat(forward_vector.shape[0], 1, 1)
    rotation_matrix[:, :3, :3] = torch.stack(
        (right_vector, up_vector, forward_vector), axis=-1)

    translation_matrix = torch.eye(4, device=origin.device).unsqueeze(
        0).repeat(forward_vector.shape[0], 1, 1)
    translation_matrix[:, :3, 3] = origin
    cam2world = (translation_matrix @ rotation_matrix)[:, :, :]
    assert (cam2world.shape[1:] == (4, 4))
    return cam2world

class Camera:
    def __init__(self, h, w):
        self.znear = 0.01
        self.zfar = 1000
        self.h = h
        self.w = w
        self.fovy = 60 / 180 * np.pi
        self.position = np.array([0.0, 0.0, -2.]).astype(np.float32)
        self.target = np.array([0.0, 0.0, 0.0]).astype(np.float32)
        self.up = -np.array([0.0, 1.0, 0.0]).astype(np.float32)
        self.yaw = np.pi / 2
        self.pitch = 0

        self.is_pose_dirty = True
        self.is_intrin_dirty = True

        self.last_x = 640
        self.last_y = 360
        self.first_mouse = True

        self.is_leftmouse_pressed = False
        self.is_rightmouse_pressed = False

        self.rot_sensitivity = -0.02
        self.trans_sensitivity = -0.01
        self.zoom_sensitivity = 0.08
        self.roll_sensitivity = 0.03
        self.target_dist = 3.
    def _global_rot_mat(self):
        x = np.array([1, 0, 0])
        z = np.cross(x, self.up)
        z = z / np.linalg.norm(z)
        x = np.cross(self.up, z)
        return np.stack([x, self.up, z], axis=-1)

    def get_view_matrix(self):
        target = torch.from_numpy(self.target).view(1,-1)
        position  =torch.from_numpy(self.position).view(1,-1)
        forward_vectors = normalize_vecs(target-position)
        return create_cam2world_matrix(forward_vectors,position).inverse()[0]
        # return np.array(glm.lookAt(self.position, self.target, self.up))

    def get_project_matrix(self):
        htanx, htany, focal = self.get_htanfovxy_focal()
        f_n = self.zfar - self.znear
        proj_mat = torch.Tensor([
            1 / htanx, 0, 0, 0,
            0, 1 / htany, 0, 0,
            0, 0, self.zfar / f_n, - 2 * self.zfar * self.znear / f_n,
            0, 0, 1, 0
        ]).reshape(4,4).to(torch.float32)
        # project_mat = glm.perspective(
        #     self.fovy,
        #     self.w / self.h,
        #     self.znear,
        #     self.zfar
        # )
        return proj_mat

    def get_htanfovxy_focal(self):
        htany = np.tan(self.fovy / 2)
        htanx = htany / self.h * self.w
        focal = self.h / (2 * htany)
        return [htanx, htany, focal]

    def get_focal(self):
        return self.h / (2 * np.tan(self.fovy / 2))

    def process_mouse(self, xpos, ypos):
        if self.first_mouse:
            self.last_x = xpos
            self.last_y = ypos
            self.first_mouse = False

        xoffset = xpos - self.last_x
        yoffset = self.last_y - ypos
        self.last_x = xpos
        self.last_y = ypos

        if self.is_leftmouse_pressed:
            self.yaw += xoffset * self.rot_sensitivity
            self.pitch += yoffset * self.rot_sensitivity

            self.pitch = np.clip(self.pitch, -np.pi / 2, np.pi / 2)

            front = np.array([np.cos(self.yaw) * np.cos(self.pitch),
                              np.sin(self.pitch), np.sin(self.yaw) *
                              np.cos(self.pitch)])
            front = self._global_rot_mat() @ front.reshape(3, 1)
            front = front[:, 0]
            self.position[:] = - front * np.linalg.norm(self.position - self.target) + self.target

            self.is_pose_dirty = True

        if self.is_rightmouse_pressed:
            front = self.target - self.position
            front = front / np.linalg.norm(front)
            right = np.cross(self.up, front)
            self.position += right * xoffset * self.trans_sensitivity
            self.target += right * xoffset * self.trans_sensitivity
            cam_up = np.cross(right, front)
            self.position += cam_up * yoffset * self.trans_sensitivity
            self.target += cam_up * yoffset * self.trans_sensitivity

            self.is_pose_dirty = True

    def process_wheel(self, dx, dy):
        front = self.target - self.position
        front = front / np.linalg.norm(front)
        self.position += front * dy * self.zoom_sensitivity
      #  self.target += front * dy * self.zoom_sensitivity
        self.is_pose_dirty = True

    def process_roll_key(self, d):
        front = self.target - self.position
        right = np.cross(front, self.up)
        new_up = self.up + right * (d * self.roll_sensitivity / np.linalg.norm(right))
        self.up = new_up / np.linalg.norm(new_up)
        self.is_pose_dirty = True

    def flip_ground(self):
        self.up = -self.up
        self.is_pose_dirty = True

    def update_target_distance(self):
        _dir = self.target - self.position
        _dir = _dir / np.linalg.norm(_dir)
        self.target = self.position + _dir * self.target_dist

    def update_resolution(self, height, width):
        self.h = max(height, 1)
        self.w = max(width, 1)
        self.is_intrin_dirty = True
g_camera = Camera(512,512)
def from_cam_to_GSCAM_dict(g_camera:Camera):
    fovy = g_camera.fovy
    fovx = g_camera.fovy
    znear = g_camera.znear
    zfar = g_camera.zfar
    world_view_transform = g_camera.get_view_matrix()

    proj_transform = g_camera.get_project_matrix()
    full_proj_transform = proj_transform@world_view_transform

    return [fovx,znear,zfar,world_view_transform,full_proj_transform]
def cursor_pos_callback(window, xpos, ypos):
    if imgui.get_io().want_capture_mouse:
        g_camera.is_leftmouse_pressed = False
        g_camera.is_rightmouse_pressed = False
    g_camera.process_mouse(xpos, ypos)

def mouse_button_callback(window, button, action, mod):
    if imgui.get_io().want_capture_mouse:
        return
    pressed = action == glfw.PRESS
    g_camera.is_leftmouse_pressed = (button == glfw.MOUSE_BUTTON_LEFT and pressed)
    g_camera.is_rightmouse_pressed = (button == glfw.MOUSE_BUTTON_RIGHT and pressed)
def wheel_callback(window, dx, dy):
    g_camera.process_wheel(dx, dy)
def key_callback(window, key, scancode, action, mods):
    if action == glfw.REPEAT or action == glfw.PRESS:
        if key == glfw.KEY_Q:
            g_camera.process_roll_key(1)
        elif key == glfw.KEY_E:
            g_camera.process_roll_key(-1)
def impl_glfw_init():
    width, height = 1280, 720
    window_name = "minimal ImGui/GLFW3 example"

    if not glfw.init():
        print("Could not initialize OpenGL context")
        sys.exit(1)

    # OS X supports only forward-compatible core profiles from 3.2
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)

    # Create a windowed mode window and its OpenGL context
    window = glfw.create_window(int(width), int(height), window_name, None, None)
    glfw.make_context_current(window)

    if not window:
        glfw.terminate()
        print("Could not initialize Window")
        sys.exit(1)

    return window

class Interface():
    def __init__(self):
        self.remote_renderer = RemoteRenderer()
        window = impl_glfw_init()
        imgui.create_context()
        self.impl = GlfwRenderer(window)
        glfw.set_cursor_pos_callback(window, cursor_pos_callback)
        glfw.set_mouse_button_callback(window, mouse_button_callback)
        glfw.set_scroll_callback(window, wheel_callback)
        glfw.set_key_callback(window, key_callback)
        self.window = window
        self.image_ids = []
        self.initialize_state=[]
       # self.create_empty_image()
       # self.send_camera = False
    def create_empty_image(self):
        from OpenGL.GL import GL_TEXTURE_2D,glTexParameteri,GL_TEXTURE_MAG_FILTER,GL_TEXTURE_MIN_FILTER,GL_LINEAR
        image_id = gl.glGenTextures(1)
        self.textureData = None
        self.initialize_state.append(False)
        gl.glBindTexture(gl.GL_TEXTURE_2D,image_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        self.image_ids.append(image_id)
    def process_remote(self):
        remote_info = self.remote_renderer.read()
        if remote_info['status']==0:
            return False
        if ("image" in remote_info):
            images = remote_info["image"]
            for i,img in enumerate(images):
                self.set_image(img,i)
            return True
        if("send" in remote_info):
            return False

    def send_camera_to_remote(self):
        gs_cam = from_cam_to_GSCAM_dict(g_camera)
        pickle_bytes = pickle.dumps(gs_cam)
        self.remote_renderer.send_cameras(pickle_bytes)
    def run(self):
        print("run")

        while not glfw.window_should_close(self.window):

            glfw.poll_events()
            self.impl.process_inputs()
            imgui.new_frame()
            imgui.begin("control panel")
            isread = imgui.button("read remote")
            imgui.end()
            if self.remote_renderer.can_read or isread:
                self.remote_renderer.can_read = True
                self.process_remote()
            for i in range(len(self.initialize_state)):
                if self.initialize_state[i]:
                    imgui.begin(f"window {i}")
                    imgui.image(self.image_ids[i], 512, 512)
                    imgui.end()
            if(self.remote_renderer.can_send):
                self.send_camera_to_remote()
            gl.glClearColor(1.0, 1.0, 1.0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            imgui.render()
            self.impl.render(imgui.get_draw_data())
            glfw.swap_buffers(self.window)

           # self.update()
        self.impl.shutdown()
        glfw.terminate()
        self.remote_renderer.socker.close()
    def set_image(self,image,window_id):
        if isinstance(image,np.ndarray):
            # image = image * 255.
            width,height = image.shape[-2],image.shape[-3]
        textureData = image
        if window_id<len(self.image_ids):
            gl.glBindTexture(gl.GL_TEXTURE_2D,self.image_ids[window_id])
        else:
            self.create_empty_image()
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, width, height, 0, gl.GL_RGB,gl.GL_UNSIGNED_BYTE, textureData)
        self.initialize_state[window_id]=True
    def get_view_matrix(self):
        return g_camera.get_view_matrix()

