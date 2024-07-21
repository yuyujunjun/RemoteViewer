Naive IMGUI for rendering and interaction. Don't actually "render" but receive an image from a third-party remote renderer (e.g. nvdiffrast or gaussian splatting).

## Base Concept

The renderer, running on the server, receives the camera from the remote viewer and sends the rendering result to the remote viewer.

On the other hand, the viewer, running on the client, receives the image from the remote renderer and sends the camera information.



### Remote Viewer

Just run python start.py. 



### Remote Renderer

#### Real-time rendering

```python
remote_viewer = RemoteViewer("xx.xx.xx.xx",12345) # set connection info
while True:
    remote_viewer.require_camera_from_remote(True) # ask for camera information
    remote_info = remote_viewer.read() # read from the network, it returns a dict
    if(remote_info["status"]==1): # status 0: failure, status 1: read success
            if("camera" in remote_info): 
                cam = remote_info['camera']
            else:
                cam = default_cam
            image = render(cam)  # run you rendering function!
            remote_viewer.send_images(image) # the image should be (H,W,3) in np.array to ensure the client can interpret
```

#### Display an image

```python
remote_viewer = RemoteViewer("xx.xx.xx.xx",12345) # set connection info
remote_viewer.send_images(image,single=True) # it will connect the client automatically and tell it that only one image will be sent, so don't wait for more images.
```

Note that after executing this function, the client will read no more data after reading this image, unless you click the button: read remote.

### More

Regarding the viewer,  I use imgui: image for presenting the image from the server. You can change it freely.

You can also change the information communicated between the server and the client. Note I use a read() function to receive all data. The send() function can be arbitrary. Just be aware that the ```socker.recv()``` in ```read()``` function will hang up until receive the data.



## ENJOY!



