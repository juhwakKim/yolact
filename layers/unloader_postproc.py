from .output_utils import postprocess
import cv2
import numpy as np
import torch


from itertools import chain
from copy import deepcopy as dp
from PIL import Image as im


def unloader_pp(det_output,h ,w, top_k = 15, score_threshold = 0.5):
    """ raw output data of Yolact -> Instance_channel, Class_channel, dictionary of Info

    Args:
        det_output (list): return of forward
        h (int): image height
        w (int): image width
        top_k (int, optional): maximum number of detected object. Defaults to 15.
        score_threshold (float, optional): score threshold. Defaults to 0.5.

    Returns:
        instance_ch (numpy.adarray): instance channel with image size
        class_ch (numpy.adarray): class channel with image size
        dict_for_YolactSegm (dictionary): {'segm_masks':List(np.int32),'seg_length': List(int), 
                                'scores' : List(np.float32), 'bboxes': List(np.int64), 
                                'image_size' : List(int) <- (h, w) , 'num_objs': int}
                                
                                segm_masks: contour x,y pixel
                                seg_length: the number of contour pixel point
                                bboxes: 2 corners coordinate for bounding boxes
                                num_objs: the number of detected
    """
    # L35, see https://github.com/dbolya/yolact/blob/master/eval.py #L149
    t = postprocess(det_output, w, h, score_threshold = score_threshold)
    
    # L37-L40, see https://github.com/dbolya/yolact/blob/master/eval.py #L155-L160
    idx = t[1].argsort(0, descending=True)[:top_k]
    
    # Masks are drawn on the GPU, so don't copy    
    masks = t[3][idx]
    classes, scores, boxes = [x[idx].cpu().numpy() for x in t[:3]]
    
    # coppied from https://github.com/dbolya/yolact/blob/master/eval.py  end.

    # masks_np is numpy and for cpu
    masks_np = (masks).byte().cpu().numpy()

    #initial var
    instance_ch = np.array(0 ,int)
    class_ch = np.array(0 ,int)
    all_new_list =[]
    tmp_list_for_YolactSegm = []

    #none instance case
    if masks_np.shape[0] == 0:
        tmp_dict_for_YolactSegm= {'seg_masks':[],'num_objs': 0, 'image_size': (h,w),
                     'seg_length':[], 'scores': [], 'bboxes': []}
        return instance_ch, class_ch, tmp_dict_for_YolactSegm


    dict_for_YolactSegm = {'num_objs': masks_np.shape[0], 'image_size': (masks_np.shape[1],masks_np.shape[2])}
    dict_for_YolactSegm.setdefault('seg_length',[])
    dict_for_YolactSegm.setdefault('scores',[])
    dict_for_YolactSegm.setdefault('bboxes',[])
    
    # make new list and sort by size(area) of mask
    for i in range(len(classes)):
        all_new_list.append({'size': masks_np[i, :, :].sum(),
                            'masks': masks_np[i, :, :], 
                            'classes': classes[i],
                            'scores': scores[i], 
                            'bboxes': boxes[i]})

    all_new_list = sorted(all_new_list, key=lambda k: k['size'], reverse = True) 

    # intergrate images
    for i in range(len(classes)):
        #class channel 
        class_ch1 = np.array(0 ,int)
        tmp_class = int(all_new_list[i]['classes'])
        class_ch1 = all_new_list[i]['masks'] * tmp_class
        cond2 = class_ch1 == tmp_class
        class_ch = np.where(cond2,class_ch1,class_ch)

        #instance channel
        all_new_list[i].update(masks = all_new_list[i]['masks']* (i+1))
        
        cond = all_new_list[i]['masks'] == i+1
        
        instance_ch = np.where(cond, all_new_list[i]['masks'], instance_ch)
   
    for i in range(len(classes)):
      
        #seperate all mask as a instance
        cond3 = np.where(instance_ch == i+1,1,0)
        cond3 = cond3.astype(np.uint8)
        #get contours for each mask
        contours, hierarchy = cv2.findContours(cond3, cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        #get the biggest mask for each contour
        contours.sort(key=cv2.contourArea, reverse=True)
       
        #flatten np.array,
        tmp_list_for_YolactSegm.append(contours[0].flatten('F'))
      
        #save seg_length
        dict_for_YolactSegm['seg_length'].append(len(contours[0]))
        #save scores
        dict_for_YolactSegm['scores'].append(all_new_list[i]['scores'])
        #save boxes
        dict_for_YolactSegm['bboxes'].append(all_new_list[i]['bboxes'])
        '''
        Check the contour result

        img3 = cv2.drawContours(cond3, [contours[0]], -1, (255,0,0), 3)
        img3 = im.fromarray(img3*50)
        img3.save('output_images/output_contour'+str(i)+'.png')
        '''
    #flatten and save list of sementation and boxes
    flatten_list = list(chain.from_iterable(tmp_list_for_YolactSegm))
    dict_for_YolactSegm['segm_masks'] = flatten_list
    bbox_flatten_list = list(chain.from_iterable(dict_for_YolactSegm['bboxes']))
    dict_for_YolactSegm['bboxes']= bbox_flatten_list
    
    """
    Check instance and class channel

    img = im.fromarray(instance_ch*10)
    img.save('output_images/output_instance.png')
    img2 = im.fromarray(class_ch*50)
    img2.save('output_images/output_class.png')
    """

    return instance_ch, class_ch, dict_for_YolactSegm