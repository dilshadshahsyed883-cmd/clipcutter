"""Standalone SCRFD/ArcFace analyzer, adapted from Clipivo's MIT-licensed face_models.py."""
import cv2
import numpy as np
from pathlib import Path

TARGET=np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]],np.float32)

def unit(v):
    v=np.asarray(v,dtype=np.float32).ravel(); n=np.linalg.norm(v)
    if not np.isfinite(n) or n<1e-8: raise ValueError('Invalid embedding')
    return v/n

class Engine:
    def __init__(self, folder, gpu=False, size=640):
        self.folder=Path(folder); self.size=size; self.gpu=gpu; self.warning=''; self.load(gpu)
    def load(self,gpu):
        import onnxruntime as ort
        avail=ort.get_available_providers(); options=ort.SessionOptions(); options.log_severity_level=3
        provider=next((p for p in ['CUDAExecutionProvider','DmlExecutionProvider','CoreMLExecutionProvider'] if p in avail),'CPUExecutionProvider') if gpu else 'CPUExecutionProvider'
        if gpu and provider!='CUDAExecutionProvider': raise RuntimeError('CUDA required for GPU analysis')
        if provider=='DmlExecutionProvider':
            options.enable_mem_pattern=False; options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        providers=[provider]+(['CPUExecutionProvider'] if provider!='CPUExecutionProvider' else [])
        try:
            self.det=ort.InferenceSession(str(self.folder/'det_10g.onnx'),sess_options=options,providers=providers)
            self.rec=ort.InferenceSession(str(self.folder/'w600k_r50.onnx'),sess_options=options,providers=providers)
        except Exception as exc:
            raise RuntimeError('Analyzer inference session initialization failed') from exc
        det_provider=self.det.get_providers()[0]; rec_provider=self.rec.get_providers()[0]
        if provider!='CPUExecutionProvider' and (det_provider!=provider or rec_provider!=provider):
            raise RuntimeError('Analyzer CUDA session fell back to CPU')
        if gpu:
            self.det.disable_fallback(); self.rec.disable_fallback()
        self.device=det_provider; self.gpu=det_provider!='CPUExecutionProvider'
        if gpu and not self.gpu: self.warning='No compatible GPU provider; using CPU'
    def get(self,image):
        return self._get(image)
    def _get(self,image):
        h,w=image.shape[:2]; s=self.size; scale=s/max(h,w); nh,nw=max(1,int(h*scale)),max(1,int(w*scale))
        canvas=np.zeros((s,s,3),np.uint8); canvas[:nh,:nw]=cv2.resize(image,(nw,nh))
        blob=cv2.dnn.blobFromImage(canvas,1/128.,(s,s),(127.5,)*3,swapRB=True)
        outputs=self.det.run(None,{self.det.get_inputs()[0].name:blob}); count=len(outputs)
        if count not in (9,15): raise ValueError('Expected SCRFD model with five landmarks')
        levels=count//3; strides=[8,16,32] if levels==3 else [8,16,32,64,128]; anchors=2 if levels==3 else 1
        boxes=[]; scores=[]; points=[]
        for i,st in enumerate(strides):
            sc=np.asarray(outputs[i]).reshape(-1); bd=np.asarray(outputs[i+levels]).reshape(-1,4)*st; pd=np.asarray(outputs[i+2*levels]).reshape(-1,5,2)*st
            centres=np.stack(np.mgrid[:s//st,:s//st][::-1],axis=-1).reshape(-1,2).astype(np.float32)*st; centres=np.repeat(centres,anchors,axis=0)
            idx=np.flatnonzero(sc>=.5); c=centres[idx]; d=bd[idx]
            boxes.extend(np.column_stack([c[:,0]-d[:,0],c[:,1]-d[:,1],c[:,0]+d[:,2],c[:,1]+d[:,3]])/scale); scores.extend(sc[idx]); points.extend((pd[idx]+c[:,None,:])/scale)
        if not boxes: return []
        boxes=np.asarray(boxes); xywh=boxes.copy(); xywh[:,2:]-=xywh[:,:2]
        keep=cv2.dnn.NMSBoxes(xywh.tolist(),[float(x) for x in scores],.5,.4)
        results=[]
        for i in np.asarray(keep).reshape(-1):
            x1,y1,x2,y2=boxes[i]; x1=max(0,int(x1)); y1=max(0,int(y1)); x2=min(w,int(np.ceil(x2))); y2=min(h,int(np.ceil(y2)))
            if min(x2-x1,y2-y1)<24: continue
            mat,_=cv2.estimateAffinePartial2D(np.asarray(points[i],np.float32),TARGET,method=cv2.LMEDS)
            if mat is None: continue
            aligned=cv2.warpAffine(image,mat,(112,112)); blob=cv2.dnn.blobFromImage(aligned,1/127.5,(112,112),(127.5,)*3,swapRB=True)
            emb=unit(self.rec.run(None,{self.rec.get_inputs()[0].name:blob})[0]); crop=image[y1:y2,x1:x2].copy()
            results.append((emb,crop,float(scores[i])*min(x2-x1,y2-y1),(x1,y1,x2,y2),float(scores[i])))
        return sorted(results,key=lambda x:x[2],reverse=True)
