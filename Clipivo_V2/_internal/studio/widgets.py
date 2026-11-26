import cv2
from PySide6.QtCore import Qt,Signal,QRectF
from PySide6.QtGui import QPainter,QColor,QImage,QPixmap,QPen
from PySide6.QtWidgets import QWidget,QSizePolicy
COLORS=['#ff7a5c','#54b8ff','#be8af7','#64ce9b','#f0c15b','#e47da7']
class Preview(QWidget):
    regionAdded=Signal(object)
    def __init__(self):
        super().__init__();self.frame=None;self.boxes=[];self.regions=[];self.armed=False;self.origin=None;self.setMinimumSize(320,220);self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    def show_frame(self,frame,boxes=()):
        rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);h,w=rgb.shape[:2];self.frame=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format_RGB888).copy();self.boxes=boxes;self.update()
    def rect_image(self):
        if self.frame is None:return QRectF()
        scale=min(self.width()/self.frame.width(),self.height()/self.frame.height());w=self.frame.width()*scale;h=self.frame.height()*scale
        return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#080a0c'));r=self.rect_image()
        if self.frame is None:p.setPen(QColor('#c7d1df'));p.drawText(self.rect(),Qt.AlignCenter,'Open a video to begin');return
        p.drawImage(r,self.frame)
        for index,(gid,name,box) in enumerate(self.boxes):
            a,b,c,d=box;p.setPen(QPen(QColor(COLORS[index%len(COLORS)]),2));p.drawRect(QRectF(r.x()+a*r.width(),r.y()+b*r.height(),(c-a)*r.width(),(d-b)*r.height()));p.drawText(int(r.x()+a*r.width()),max(15,int(r.y()+b*r.height())-4),name)
        p.setPen(QPen(QColor('#ffae62'),2,Qt.DashLine))
        for a,b,c,d in self.regions:p.drawRect(QRectF(r.x()+a*r.width(),r.y()+b*r.height(),(c-a)*r.width(),(d-b)*r.height()))
    def mousePressEvent(self,event):
        if self.armed and self.rect_image().contains(event.position()):self.origin=event.position()
    def mouseReleaseEvent(self,event):
        if self.origin is None:return
        r=self.rect_image();clip=lambda v:max(0,min(1,v));x=sorted([clip((self.origin.x()-r.x())/r.width()),clip((event.position().x()-r.x())/r.width())]);y=sorted([clip((self.origin.y()-r.y())/r.height()),clip((event.position().y()-r.y())/r.height())]);self.origin=None;self.armed=False
        if x[1]-x[0]>.01 and y[1]-y[0]>.01:self.regionAdded.emit([x[0],y[0],x[1],y[1]])

class Timeline(QWidget):
    seekRequested=Signal(float)
    def __init__(self):
        super().__init__();self.data=None;self.position=0.;self.solo=None;self.ignored=True;self.setMinimumHeight(150)
    def visible(self):return [g for g in (self.data or {}).get('people',[]) if (self.ignored or not (g.get('ignored') or g.get('filtered'))) and (not self.solo or g['id']==self.solo)]
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#171b22'));w=max(1,self.width()-135);d=max(.001,(self.data or {}).get('duration',1));groups=self.visible();self.setMinimumHeight(max(150,35+len(groups)*30))
        for i in range(6):
            x=125+w*i/5;p.setPen(QColor('#8793a5'));p.drawText(int(x),18,f'{d*i/5:.1f}s')
        for i,g in enumerate(groups):
            y=30+i*30;p.setPen(QColor('#dce3ee'));p.drawText(5,y+16,g['name'][:18]);p.fillRect(QRectF(125,y,w,22),QColor('#252c36'))
            for a,b in g.get('segments',[]):p.fillRect(QRectF(125+a/d*w,y,max(2,(b-a)/d*w),22),QColor('#697280' if g.get('ignored') or g.get('filtered') else COLORS[i%len(COLORS)]))
        p.setPen(QPen(QColor('#ffb44f'),2));x=125+self.position/d*w;p.drawLine(int(x),22,int(x),self.height())
    def mousePressEvent(self,event):
        if self.data:self.seekRequested.emit(max(0,min(self.data['duration'],(event.position().x()-125)/max(1,self.width()-135)*self.data['duration'])))
