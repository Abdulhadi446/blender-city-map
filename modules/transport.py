#!/usr/bin/env python3
"""transport.py — Transport module (headless)."""
from __future__ import annotations
import json, math, os, sys, time
ROOT = "/home/abdulhadi/Work/city"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT + "/modules")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import citykit as ck
import bpy
OUT_BLEND = os.path.join(ck.OUT_DIR, "transport.blend")
PREV_A = os.path.join(ck.OUT_DIR, "transport_preview.png")
PREV_B = os.path.join(ck.OUT_DIR, "transport_airport_preview.png")
REPORT_MD = os.path.join(ck.REPORTS_DIR, "transport_report.md")
LAYOUT = ck.read_layout()
PROGRAM = json.load(open(os.path.join(ck.REPORTS_DIR, "program.json")))
FACILITIES = [f for f in PROGRAM["facilities"] if f.get("owning_module") == "Transport"]
PARCELS = {p["id"]: p for p in LAYOUT["parcels"]}
COLL = ck.ensure_collection("Transport")
MESH_COLL = ck.ensure_collection("Meshes", parent=COLL)
COLL_COLL = ck.ensure_collection("Colliders", parent=COLL)
LIGHT_COLL = ck.ensure_collection("Lights", parent=COLL)
FAC_OBJS = {}
LIGHT_N = [0]
T0 = time.time()

class Builder(object):
    def __init__(self):
        self.v=[];self.f=[];self.mi=[];self.mats=[]
    def midx(self,name):
        for i,x in enumerate(self.mats):
            if x==name: return i
        self.mats.append(name); return len(self.mats)-1
    def poly(self,pts,mat):
        i=self.midx(mat); n=len(self.v); self.v.extend(pts); self.f.append(tuple(range(n,n+len(pts)))); self.mi.append(i)
    def box(self,x0,y0,z0,x1,y1,z1,mat):
        if x1<x0: x0,x1=x1,x0
        if y1<y0: y0,y1=y1,y0
        if z1<z0: z0,z1=z1,z0
        i=self.midx(mat); n=len(self.v)
        self.v.extend([(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)])
        for ff in ((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            self.f.append(tuple(n+k for k in ff)); self.mi.append(i)
    def cyl(self,cx,cy,z0,z1,r,mat,seg=8,cap=True):
        i=self.midx(mat); n=len(self.v)
        for k in range(seg):
            a=2*math.pi*k/seg; self.v.append((cx+r*math.cos(a),cy+r*math.sin(a),z0))
        for k in range(seg):
            a=2*math.pi*k/seg; self.v.append((cx+r*math.cos(a),cy+r*math.sin(a),z1))
        for k in range(seg):
            k2=(k+1)%seg; self.f.append((n+k,n+k2,n+seg+k2,n+seg+k)); self.mi.append(i)
        if cap:
            self.f.append(tuple(n+k for k in range(seg))); self.mi.append(i)
            self.f.append(tuple(n+seg+k for k in reversed(range(seg)))); self.mi.append(i)

def make_mesh(name,bd,coll,loc=None,rot=0.0):
    me=bpy.data.meshes.new(name); me.from_pydata(bd.v,[],bd.f); me.update()
    for n in bd.mats: me.materials.append(ck.append_material(n))
    for p,mi in zip(me.polygons,bd.mi): p.material_index=int(mi)
    ob=bpy.data.objects.new(name,me)
    if loc is not None: ob.location=(float(loc[0]),float(loc[1]),float(loc[2]))
    if rot: ob.rotation_euler=(0,0,math.radians(float(rot)))
    coll.objects.link(ob); return ob

def make_kit(name,bd): return make_mesh(name,bd,MESH_COLL,loc=(0,0,0,))
def instance_kit(base,name,loc,rot_z=0.0):
    ob=bpy.data.objects.new(name,base.data); ob.location=(float(loc[0]),float(loc[1]),float(loc[2])); ob.rotation_euler=(0,0,math.radians(float(rot_z))); MESH_COLL.objects.link(ob); return ob
def add_collider(fid,rect,height):
    x0,y0,x1,y1=rect; bd=Builder(); bd.box(x0,y0,0.0,x1,y1,max(float(height),0.5),"col_placeholder"); return make_mesh("COL_"+fid,bd,COLL_COLL)
def add_light(loc,energy=200.0,ltype="POINT",color=(1,1,1),name=None):
    global LIGHT_N
    LIGHT_N[0]+=1
    if name is None: name="LT_trn_%02d"%LIGHT_N[0]
    ld=bpy.data.lights.new(name,type=ltype)
    try: ld.energy=energy
    except: pass
    try: ld.color=color
    except: pass
    ob=bpy.data.objects.new(name,ld); ob.location=(float(loc[0]),float(loc[1]),float(loc[2])); LIGHT_COLL.objects.link(ob); return ob
def reg(fid,*objs):
    FAC_OBJS.setdefault(fid,[])
    for o in objs:
        if o is not None: FAC_OBJS[fid].append(o)
def slab(bd,rect,z0=0.0,z1=0.12,mat="sidewalk_concrete"):
    x0,y0,x1,y1=rect; bd.box(x0,y0,z0,x1,y1,z1,mat)
def walls_rect(bd,rect,h,mat,t=0.25,open_side=None,open_w=None):
    x0,y0,x1,y1=rect
    if open_side=="S":
        if open_w is None: open_w=(x1-x0)*0.5
        cx=(x0+x1)*0.5; a,b=cx-open_w*0.5,cx+open_w*0.5
        bd.box(x0,y0,0.0,a,y0+t,h,mat); bd.box(b,y0,0.0,x1,y0+t,h,mat)
    else: bd.box(x0,y0,0.0,x1,y0+t,h,mat)
    if open_side=="N":
        if open_w is None: open_w=(x1-x0)*0.5
        cx=(x0+x1)*0.5; a,b=cx-open_w*0.5,cx+open_w*0.5
        bd.box(x0,y1-t,0.0,a,y1,h,mat); bd.box(b,y1-t,0.0,x1,y1,h,mat)
    else: bd.box(x0,y1-t,0.0,x1,y1,h,mat)
    bd.box(x0,y0,0.0,x0+t,y1,h,mat); bd.box(x1-t,y0,0.0,x1,y1,h,mat)
def roof_rect(bd,rect,z,h=0.3,mat="roof_metal",over=0.5):
    x0,y0,x1,y1=rect; bd.box(x0-over,y0-over,z,x1+over,y1+over,z+h,mat)
def building(bd,rect,h,mat_wall="concrete",mat_roof="roof_metal",open_side=None,open_w=None):
    slab(bd,rect,0.0,0.2,"concrete"); walls_rect(bd,rect,h,mat_wall,0.25,open_side,open_w); roof_rect(bd,rect,h,0.3,mat_roof)

def build_runway(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); slab(bd,rect,0,0.2,"asphalt")
    bd.box(x0-60,y0-6,0,x0,y1+6,0.15,"gravel"); bd.box(x1,y0-6,0,x1+60,y1+6,0.15,"gravel")
    cx=(y0+y1)/2; x=x0+30
    while x<x1-30:
        bd.box(x,cx-0.25,0.21,min(x+30,x1-5),cx+0.25,0.22,"marking_white"); x+=70
    for xx in (x0+15,x1-35):
        for i in range(7):
            yy=y0+2+i*((y1-y0-4)/6.0); bd.box(xx,yy,0.21,xx+20,yy+2.5,0.22,"marking_white")
    for xx in (x0+50,x1-90):
        for i in range(3): bd.box(xx+i*6,cx-6,0.21,xx+i*6+4,cx+6,0.22,"marking_white")
    for i in range(0,int((x1-x0)/100)+1):
        xx=x0+i*100
        if xx>x1: break
        for yy in (y0+0.8,y1-0.8): bd.box(xx-0.25,yy-0.25,0.21,xx+0.25,yy+0.25,0.45,"emissive_warm")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,0.25)
    add_light(((x0+x1)/2,(y0+y1)/2,4),300,"POINT",(1,0.95,0.8))

def build_simple_strip(f,rect,mat="asphalt"):
    bd=Builder(); slab(bd,rect,0,0.2,mat); ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,0.25)

def build_terminal(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=6.8
    slab(bd,rect,0,0.35,"concrete"); bd.box(x0,y0,3.2,x1,y1,3.45,"concrete")
    t=0.25
    bd.box(x0,y1-t,0,x1,y1,h,"concrete"); bd.box(x0,y0,0,x0+t,y1,h,"concrete"); bd.box(x1-t,y0,0,x1,y1,h,"concrete")
    span=x1-x0; n_gates=6; gate_w=6.0; gap=(span-n_gates*gate_w)/(n_gates+1); cur=x0; segs=[]
    for i in range(n_gates):
        g0=cur+gap; g1=g0+gate_w
        if g0>cur+0.1: segs.append((cur,g0))
        bd.box(g0,y0,2.4,g1,y0+t,h,"glass_shop"); cur=g1
    if cur<x1-0.1: segs.append((cur,x1))
    for a,b in segs: bd.box(a,y0,0,b,y0+t,h,"concrete")
    roof_rect(bd,rect,h,0.4,"roof_metal",1.0)
    truss_bd=Builder()
    truss_bd.box(-0.15,-0.5,0,0.15,0.5,0.25,"metal_steel"); truss_bd.box(-0.15,-0.5,h-0.4,0.15,0.5,h,"metal_steel"); truss_bd.box(-0.1,-0.1,0,0.1,0.1,h,"metal_steel")
    truss_base=make_kit("TRN_truss",truss_bd); trusses=[]
    for i in range(12):
        xx=x0+(i+0.5)*(span/12.0); trusses.append(instance_kit(truss_base,"SM_Truss_%s_%02d"%(f["id"],i),(xx,(y0+y1)/2,0),0))
    for i in range(8):
        xx=x0+20+i*7.5; bd.box(xx,y1-8,0,xx+4,y1-6.5,1.1,"concrete"); bd.box(xx,y1-8,1.1,xx+4,y1-6.5,1.25,"glass_shop")
    bench_bd=Builder(); bench_bd.box(-1.2,-0.35,0,1.2,0.35,0.45,"metal_painted_dark"); bench_bd.box(-1.2,-0.35,0.45,1.2,0.35,0.5,"wood_painted")
    bench_base=make_kit("TRN_bench",bench_bd); benches=[]
    for r in range(5):
        for c in range(10):
            benches.append(instance_kit(bench_base,"SM_Bench_%s_%02d_%02d"%(f["id"],r,c),(x0+15+c*6.0,y0+6+r*3.0,0),0))
    for j in range(2):
        jx=x0+120+j*220; bd.box(jx-1.5,y0-22,0,jx+1.5,y0,3.0,"metal_painted_dark"); bd.box(jx-1.2,y0-22,0,jx+1.2,y0,2.8,"glass_dark")
    fo=2.0
    bd.box(x0-fo,y0-fo,0,x1+fo,y0-fo+0.15,2.0,"metal_painted_dark"); bd.box(x0-fo,y1+fo-0.15,0,x1+fo,y1+fo,2.0,"metal_painted_dark")
    bd.box(x0-fo,y0-fo,0,x0-fo+0.15,y1+fo,2.0,"metal_painted_dark"); bd.box(x1+fo-0.15,y0-fo,0,x1+fo,y1+fo,2.0,"metal_painted_dark")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob,*trusses,*benches); add_collider(f["id"],rect,h)
    add_light(((x0+x1)/2,(y0+y1)/2,h-0.5),500,"POINT",(0.9,0.95,1.0))
    add_light((x0+100,y0-10,3),250,"POINT",(1,1,0.9)); add_light((x1-100,y0-10,3),250,"POINT",(1,1,0.9))

def build_tower(f,rect):
    x0,y0,x1,y1=rect; cx,cy=(x0+x1)/2,(y0+y1)/2; bd=Builder()
    bd.box(x0,y0,0,x1,y1,4,"concrete")
    s=8; bd.box(cx-s/2,cy-s/2,4,cx+s/2,cy+s/2,24,"concrete")
    c=12; bd.box(cx-c/2,cy-c/2,24,cx+c/2,cy+c/2,28,"metal_painted_dark")
    bd.box(cx-c/2+0.2,cy-c/2+0.2,24.5,cx+c/2-0.2,cy+c/2-0.2,27.5,"glass_office")
    bd.box(cx-c/2-0.5,cy-c/2-0.5,28,cx+c/2+0.5,cy+c/2+0.5,28.5,"roof_metal")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,28.5); add_light((cx,cy,26),400,"POINT",(0.9,0.95,1.0))

def build_hangars(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); n=3; w=(x1-x0)/n
    for i in range(n):
        hx0=x0+i*w+1; hx1=x0+(i+1)*w-1; hy0=y0; hy1=y1; hh=12.0
        slab(bd,(hx0,hy0,hx1,hy1),0,0.25,"concrete")
        bd.box(hx0,hy1-0.25,0,hx1,hy1,hh,"metal_painted_dark")
        bd.box(hx0,hy0,0,hx0+0.25,hy1,hh,"metal_painted_dark"); bd.box(hx1-0.25,hy0,0,hx1,hy1,hh,"metal_painted_dark")
        roof_rect(bd,(hx0,hy0,hx1,hy1),hh,0.4,"roof_metal",1.0)
        for j in range(6):
            xx=hx0+(j+0.5)*(hx1-hx0)/6.0; bd.box(xx-0.1,hy0,hh-0.6,xx+0.1,hy1,hh-0.4,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,12.5)

def build_fire_station(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=8.0
    building(bd,rect,h,"concrete","roof_metal",open_side="S",open_w=12.0)
    cx=x1-8; bd.box(cx,y0,0,cx+6,y0+6,18,"concrete"); bd.box(cx+0.5,y0+0.5,2,cx+5.5,y0+5.5,17.5,"glass_dark")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,18.0)

def build_cargo(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=8.0
    building(bd,rect,h,"concrete","roof_metal",open_side="S",open_w=(x1-x0)*0.9)
    span=x1-x0
    for i in range(12):
        xx=x0+(i+0.5)*span/12.0; bd.box(xx-1.2,y0,0,xx+1.2,y0+0.15,2.6,"metal_painted_dark")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,h)

def build_air_parking(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); slab(bd,rect,0,0.12,"asphalt")
    for i in range(8):
        yy=y0+20+i*38
        for j in range(6):
            xx=x0+8+j*11; bd.box(xx,yy,0.13,xx+0.15,yy+6,0.14,"marking_white")
    for i in range(3):
        yy=y0+40+i*100; bd.box(x0+2,yy,3.0,x1-2,yy+2,3.3,"roof_metal")
        for k in range(4):
            xx=x0+10+k*((x1-x0-20)/3.0); bd.box(xx,yy,0,xx+0.2,yy+0.2,3.0,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,3.5)

def build_bus_depot(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=6.0
    brect=(x0+5,y1-45,x1-5,y1-5); building(bd,brect,h,"concrete","roof_metal",open_side="S",open_w=(brect[2]-brect[0])*0.6)
    bd.box(x0+5,y0+5,4.5,x1-5,y1-55,5.0,"roof_metal")
    for i in range(6):
        xx=x0+15+i*((x1-x0-30)/5.0); bd.box(xx,y0+5,0,xx+0.25,y1-55,4.5,"metal_steel")
    for i in range(26):
        yy=y0+4+(i%13)*10; xx=x0+8+(i//13)*((x1-x0)/2.0-10); bd.box(xx,yy,0.13,xx+0.15,yy+7,0.14,"marking_yellow")
    bd.box((x0+x1)/2-6,y0+8,0,(x0+x1)/2+6,y0+14,3.0,"metal_painted_dark")
    bd.box((x0+x1)/2-5,y0+9,3.0,(x0+x1)/2+5,y0+13,3.3,"roof_metal")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,6.5)

def build_mail_sorting(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=7.0; building(bd,rect,h,"concrete","roof_bitumen")
    for i in range(24):
        xx=x0+4+i*((x1-x0-8)/23.0); bd.box(xx,y0,0,xx+2.0,y0+0.15,1.2,"concrete"); bd.box(xx+0.3,y0+0.15,0.2,xx+1.7,y0+0.2,2.4,"metal_painted_dark")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,h)

def build_park_and_ride(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); slab(bd,rect,0,0.12,"asphalt")
    for i in range(12):
        yy=y0+8+i*12
        for j in range(10):
            xx=x0+6+j*11; bd.box(xx,yy,0.13,xx+0.12,yy+7,0.14,"marking_white")
    for i in range(4):
        yy=y0+20+i*35; bd.box(x0+4,yy,3.0,x1-4,yy+2,3.3,"roof_metal")
        for k in range(3):
            xx=x0+15+k*((x1-x0-30)/2.0); bd.box(xx,yy,0,xx+0.2,yy+0.2,3.0,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,3.5)

def build_coach_terminal(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=7.5
    brect=(x0+5,y1-50,x1-5,y1-5); building(bd,brect,h,"glass_shop","roof_metal",open_side="S",open_w=(brect[2]-brect[0])*0.7)
    for i in range(12):
        xx=x0+10+i*((x1-x0-20)/11.0); bd.box(xx,y0+10,0.13,xx+0.2,y0+35,0.14,"marking_yellow"); bd.box(xx+0.2,y0+10,0.13,xx+12,y0+12,0.14,"marking_yellow")
    bd.box(x0+5,y0+5,4.2,x1-5,y1-55,4.7,"roof_metal")
    for i in range(5):
        xx=x0+20+i*((x1-x0-40)/4.0); bd.box(xx,y0+5,0,xx+0.25,y1-55,4.2,"metal_steel")
    bench_bd=Builder(); bench_bd.box(-1.0,-0.3,0,1.0,0.3,0.45,"metal_painted_dark")
    bench_base=make_kit("TRN_coach_bench",bench_bd); benches=[]
    for r in range(3):
        for c in range(6):
            benches.append(instance_kit(bench_base,"SM_CoachBench_%d_%d"%(r,c),(x0+20+c*5,y1-35+r*4,0),0))
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob,*benches); add_collider(f["id"],rect,8.0)
    add_light(((x0+x1)/2,(y0+y1)/2,6),450,"POINT",(0.95,0.95,1.0))

def build_petrol_ev(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=4.0
    brect=(x0+5,y1-40,x1-5,y1-5); building(bd,brect,h,"glass_shop","roof_metal",open_side="S",open_w=(brect[2]-brect[0])*0.6)
    c1=(x0+5,y0+8,x0+(x1-x0)*0.55,y0+45); bd.box(c1[0],c1[1],3.2,c1[2],c1[3],3.5,"roof_metal")
    for i in range(3):
        xx=c1[0]+5+i*((c1[2]-c1[0]-10)/2.0); bd.box(xx,c1[1]+2,0,xx+0.2,c1[1]+4,3.2,"metal_steel")
    c2=(x0+(x1-x0)*0.6,y0+8,x1-5,y0+45); bd.box(c2[0],c2[1],3.2,c2[2],c2[3],3.5,"roof_metal")
    for i in range(3):
        xx=c2[0]+5+i*((c2[2]-c2[0]-10)/2.0); bd.box(xx,c2[1]+2,0,xx+0.2,c2[1]+4,3.2,"metal_steel")
    for i in range(6):
        xx=c1[0]+6+i*6; bd.box(xx,(c1[1]+c1[3])/2-0.4,0,xx+0.8,(c1[1]+c1[3])/2+0.4,1.6,"metal_painted_dark")
    for i in range(8):
        xx=c2[0]+4+i*5; bd.box(xx,(c2[1]+c2[3])/2-0.3,0,xx+0.6,(c2[1]+c2[3])/2+0.3,1.2,"metal_painted_dark")
    bd.box(x0+5,y0+50,0,x0+35,y0+80,3.5,"concrete"); bd.box(x0+5,y0+50,3.5,x0+35,y0+80,3.8,"roof_metal")
    bd.box(x1-12,y0+5,0,x1-5,y0+12,1.8,"metal_painted_dark")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,4.0)

def build_truck_stop(f,rect):
    x0,y0,x1,y1=rect; bd=Builder()
    brect=(x0+5,y1-45,x0+60,y1-5); building(bd,brect,4.5,"concrete","roof_metal")
    wrect=(x0+65,y1-45,x1-5,y1-5); building(bd,wrect,5.0,"concrete","roof_metal",open_side="S",open_w=(wrect[2]-wrect[0])*0.8)
    for i in range(24):
        xx=x0+5+(i%12)*12; yy=y0+5+(i//12)*25; bd.box(xx,yy,0.13,xx+0.2,yy+18,0.14,"marking_yellow")
    bd.box((x0+x1)/2-4,y0+5,0,(x0+x1)/2+4,y0+12,0.3,"concrete")
    bd.box(x0+5,y0+55,4.0,x0+50,y0+85,4.4,"roof_metal")
    for i in range(3):
        xx=x0+10+i*15; bd.box(xx,y0+57,0,xx+0.25,y0+59,4.0,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,5.5)

def build_rail_line(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); bd.box(x0,y0,0,x1,y1,0.3,"gravel")
    for i in range(4):
        yy=y0+3+i*4; bd.box(x0,yy,0.31,x1,yy+0.12,0.42,"metal_steel")
    x=x0
    while x<x1:
        bd.box(x,y0+1,0.25,x+2.0,y1-1,0.32,"wood_old"); x+=5.0
    x=x0+50
    while x<x1:
        bd.box(x-0.2,(y0+y1)/2-0.2,0,x+0.2,(y0+y1)/2+0.2,6.0,"metal_steel")
        bd.box(x-2.0,(y0+y1)/2-0.1,5.8,x+2.0,(y0+y1)/2+0.1,6.0,"metal_steel"); x+=100.0
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,6.5)

def build_rail_platforms(f,rect):
    x0,y0,x1,y1=rect; bd=Builder()
    bd.box(x0,y0,0,x1,y1,0.35,"concrete"); bd.box(x0,y0,4.5,x1,y1,4.8,"roof_metal")
    x=x0+10
    while x<x1:
        bd.box(x,y0+1,0,x+0.3,y0+2.0,4.5,"metal_steel"); bd.box(x,y1-2.0,0,x+0.3,y1-1.0,4.5,"metal_steel"); x+=25.0
    for i in range(4):
        xx=x0+80+i*150; bd.box(xx,y1,0,xx+6,y1+4,0.2,"concrete")
        for k in range(6): bd.box(xx,y1+k*0.7,0.2+k*0.5,xx+6,y1+0.6+k*0.7,0.7+k*0.5,"concrete")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,5.0)

def build_rail_station(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=8.0; slab(bd,rect,0,0.3,"concrete")
    t=0.25
    bd.box(x0,y1-t,0,x1,y1,h,"glass_shop"); bd.box(x0,y0,0,x0+t,y1,h,"concrete"); bd.box(x1-t,y0,0,x1,y1,h,"concrete")
    for i in range(8):
        xx=x0+i*((x1-x0)/7.0); bd.box(xx-0.4,y0,0,xx+0.4,y0+t,h,"concrete")
    roof_rect(bd,rect,h,0.4,"roof_metal",1.0)
    truss_bd=Builder(); truss_bd.box(-0.15,-0.5,0,0.15,0.5,0.2,"metal_steel"); truss_bd.box(-0.15,-0.5,h-0.3,0.15,0.5,h,"metal_steel"); truss_bd.box(-0.1,-0.1,0,0.1,0.1,h,"metal_steel")
    truss_base=make_kit("TRN_rail_truss",truss_bd); trusses=[]; span=x1-x0
    for i in range(14):
        xx=x0+(i+0.5)*span/14.0; trusses.append(instance_kit(truss_base,"SM_RailTruss_%02d"%i,(xx,(y0+y1)/2,0),0))
    bd.box(x0+span*0.45,y0-25,6.0,x0+span*0.55,y1+5,6.4,"concrete")
    for i in range(4):
        xx=x0+60+i*150; bd.box(xx,y1-1.5,2.0,xx+4,y1-1.0,4.0,"sign_metal")
    for i in range(2):
        xx=x0+100+i*400
        for k in range(8): bd.box(xx,y1+k*0.8,0.2+k*0.4,xx+8,y1+0.7+k*0.8,0.7+k*0.4,"concrete")
    carriage_bd=Builder(); carriage_bd.box(-12,-1.5,0,12,1.5,3.2,"metal_painted_dark"); carriage_bd.box(-11,-1.3,0.5,11,1.3,2.8,"glass_dark")
    carriage_base=make_kit("TRN_carriage",carriage_bd); cars=[]
    for consist in range(2):
        base_x=x0+40+consist*300
        for c in range(4): cars.append(instance_kit(carriage_base,"SM_Car_%d_%d"%(consist,c),(base_x+c*26,1467.0,0.3),0))
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob,*trusses,*cars); add_collider(f["id"],rect,8.5)
    for i in range(4): add_light((x0+(i+0.5)*span/4.0,(y0+y1)/2,4.2),150,"POINT",(1,0.95,0.8))

def build_metro_entrance(f,rect):
    x0,y0,x1,y1=rect; cx,cy=(x0+x1)/2,(y0+y1)/2; bd=Builder()
    slab(bd,rect,0,0.2,"concrete"); bd.box(x0,y0,0,x1,y1,0.6,"concrete")
    bd.box(cx-2,cy-2,0,cx+2,cy+2,4.0,"concrete"); bd.box(cx-1.7,cy-1.7,0.5,cx+1.7,cy+1.7,3.8,"glass_dark")
    bd.box(x0+1,y0+1,0,x0+4,y0+4,1.5,"metal_painted_dark")
    bd.box(x0-0.5,y0-0.5,3.6,x1+0.5,y1+0.5,3.9,"roof_metal")
    bd.box(x0-0.5,y0-0.5,3.9,x0+0.3,y0+0.3,4.1,"metal_steel"); bd.box(x1-0.3,y1-0.3,3.9,x1+0.5,y1+0.5,4.1,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,4.2)

def build_carpark_multistorey(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=3.2; floors=4
    for k in range(floors):
        z=k*h; bd.box(x0,y0,z,x1,y1,z+0.25,"concrete")
    for k in range(floors):
        z=k*h
        bd.box(x0,y0,z,x1,y0+0.25,z+h,"concrete"); bd.box(x0,y1-0.25,z,x1,y1,z+h,"concrete")
        bd.box(x0,y0,z,x0+0.25,y1,z+h,"concrete"); bd.box(x1-0.25,y0,z,x1,y1,z+h,"concrete")
    for k in range(floors-1):
        z=k*h; bd.box(x0+2,y0+2,z,x0+12,y0+14,z+h,"concrete")
    roof_rect(bd,rect,floors*h,0.3,"roof_metal",0.5)
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,floors*h+0.5)

def build_ind_depot(f,rect):
    parcels=f["placement"].get("parcel_ids",[]); rects=[]
    for pid in parcels:
        p=PARCELS.get(pid)
        if p and "rect" in p: rects.append(p["rect"])
    if not rects: rects=[rect]
    bd=Builder()
    for r in rects:
        x0,y0,x1,y1=r; h=6.4; building(bd,r,h,"concrete","roof_metal",open_side="S",open_w=(x1-x0)*0.5)
        cx=(x0+x1)/2; bd.box(cx-3,y0,0,cx+3,y0+0.15,2.6,"metal_painted_dark")
    xs=[r[0] for r in rects]+[r[2] for r in rects]; ys=[r[1] for r in rects]+[r[3] for r in rects]
    bbox=(min(xs),min(ys),max(xs),max(ys))
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],bbox,6.5)

def build_street_depot(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=6.0
    brect=(x0+5,y1-60,x0+70,y1-5); building(bd,brect,h+2,"concrete","roof_metal")
    vrect=(x0+75,y0+5,x1-5,y1-5); building(bd,vrect,h,"concrete","roof_metal",open_side="S",open_w=(vrect[2]-vrect[0])*0.8)
    bd.box(x0+10,y0+10,0,x0+40,y0+40,3.0,"sand")
    bd.box(x0+5,y0+5,0,x0+35,y0+30,4.0,"concrete"); bd.box(x0+5,y0+5,4.0,x0+35,y0+30,4.3,"roof_metal")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,8.5)

def build_trk_parking(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); slab(bd,rect,0,0.12,"asphalt")
    for i in range(6):
        yy=y0+8+i*18
        for j in range(8):
            xx=x0+6+j*16
            if xx+4>x1: continue
            bd.box(xx,yy,0.13,xx+0.12,yy+6,0.14,"marking_white")
    for i in range(2):
        yy=y0+20+i*60; bd.box(x0+4,yy,3.0,x1-4,yy+2,3.3,"roof_metal")
        for k in range(3):
            xx=x0+15+k*((x1-x0-30)/2.0); bd.box(xx,yy,0,xx+0.2,yy+0.2,3.0,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,3.5)

def build_trk_gate(f,rect):
    x0,y0,x1,y1=rect; bd=Builder(); h=5.0
    brect=(x0+5,y1-40,x1-5,y1-5); building(bd,brect,h,"concrete","roof_metal")
    for i in range(10):
        xx=x0+8+i*14; bd.box(xx,y0+5,0.13,xx+0.15,y0+40,0.14,"marking_yellow")
    bd.box(x0+5,y0+45,0,x1-5,y0+55,0.15,"concrete")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,5.5)

def build_trk_hub(f,rect):
    x0,y0,x1,y1=rect; bd=Builder()
    for i in range(8):
        yy=y0+10+i*18; bd.box(x0+5,yy,0,x0+8,yy+12,0.15,"concrete"); bd.box(x0+8,yy,0.13,x0+40,yy+0.15,0.14,"marking_yellow")
    bd.box(x0+45,y0+10,0,x1-5,y0+60,0.35,"concrete")
    bd.box(x0+5,y0+5,4.0,x1-5,y1-5,4.4,"roof_metal")
    for i in range(4):
        xx=x0+15+i*((x1-x0-30)/3.0); bd.box(xx,y0+5,0,xx+0.25,y1-5,4.0,"metal_steel")
    bd.box(x0+5,y1-40,0,x0+60,y1-5,0.15,"concrete")
    for i in range(10):
        xx=x0+8+i*5; bd.box(xx,y1-35,0,xx+0.1,y1-25,1.0,"metal_steel")
    ob=make_mesh(f["id"],bd,MESH_COLL); reg(f["id"],ob); add_collider(f["id"],rect,4.5)

BUILDERS={
 "TRN_RUNWAY":build_runway,
 "TRN_TAXIWAY":lambda f,r:build_simple_strip(f,r,"asphalt"),
 "TRN_APRON":lambda f,r:build_simple_strip(f,r,"asphalt"),
 "TRN_AIR_TERMINAL":build_terminal,
 "TRN_AIR_TOWER":build_tower,
 "TRN_AIR_HANGARS":build_hangars,
 "TRN_AIR_FIRE":build_fire_station,
 "TRN_AIR_CARGO":build_cargo,
 "TRN_AIR_PARKING":build_air_parking,
 "TRN_BUS_DEPOT":build_bus_depot,
 "TRN_MAIL_SORTING":build_mail_sorting,
 "TRN_PARK_AND_RIDE":build_park_and_ride,
 "TRN_COACH_TERMINAL":build_coach_terminal,
 "TRN_PETROL_EV":build_petrol_ev,
 "TRN_TRUCK_STOP":build_truck_stop,
 "TRN_RAIL_LINE":build_rail_line,
 "TRN_RAIL_PLATFORMS":build_rail_platforms,
 "TRN_RAIL_STATION":build_rail_station,
 "TRN_STREET_DEPOT":build_street_depot,
 "CARPARK_MULTISTOREY":build_carpark_multistorey,
 "IND_DEPOT":build_ind_depot,
 "METRO_ENT_1":build_metro_entrance,
 "METRO_ENT_2":build_metro_entrance,
 "METRO_ENT_3":build_metro_entrance,
 "METRO_ENT_4":build_metro_entrance,
 "METRO_ENT_5":build_metro_entrance,
 "TRK_PARKING_E1":build_trk_parking,
 "TRK_PARKING_E2":build_trk_parking,
 "TRK_PARKING_E3":build_trk_parking,
 "TRK_GATE_E":build_trk_gate,
 "TRK_TRANSPORT_HUB":build_trk_hub,
}

for f in FACILITIES:
    fid=f["id"]
    rect=f["placement"].get("rect")
    if rect is None:
        pid=f["placement"].get("parcel_ids",[None])[0]
        p=PARCELS.get(pid) if pid else None
        rect=p["rect"] if p else None
    print("[transport] building",fid,rect,flush=True)
    fn=BUILDERS.get(fid)
    if fn is None:
        print("[transport] WARNING no builder for",fid,flush=True)
        bd=Builder(); slab(bd,rect,0,0.2,"concrete"); ob=make_mesh(fid,bd,MESH_COLL); reg(fid,ob); add_collider(fid,rect,3.0)
    else:
        fn(f,rect)
    # colliders already created by builders

# apron markings
apron_f=next((f for f in FACILITIES if f["id"]=="TRN_APRON"),None)
if apron_f:
    r=apron_f["placement"]["rect"]; x0,y0,x1,y1=r; bd=Builder()
    for i in range(6):
        xx=x0+80+i*150; bd.box(xx-0.2,y0+2,0.13,xx+0.2,y1-2,0.14,"marking_yellow")
        bd.box(xx-8,y0+2,0.13,xx-7.8,y0+25,0.14,"marking_white"); bd.box(xx+7.8,y0+2,0.13,xx+8,y0+25,0.14,"marking_white")
    for i in range(6):
        xx=x0+70+i*150; bd.box(xx-2,y0+5,0,xx+2,y0+9,1.2,"metal_painted_dark")
    ob=make_mesh("TRN_APRON_MARKINGS",bd,MESH_COLL); reg("TRN_APRON",ob)

runway_f=next((f for f in FACILITIES if f["id"]=="TRN_RUNWAY"),None)
if runway_f:
    r=runway_f["placement"]["rect"]; add_light(((r[0]+r[2])/2,(r[1]+r[3])/2,6),200,"POINT",(1,0.95,0.8))

ck.update_view()
ck.save_blend(OUT_BLEND)

try:
    ck.make_preview(PREV_A,cam_pos=(-400,-1000,350),cam_target=(0,-1200,20),engine="BLENDER_EEVEE")
except Exception as e:
    print("[transport] preview A failed:",e,flush=True)
try:
    ck.make_preview(PREV_B,cam_pos=(-100,-1480,120),cam_target=(-100,-1440,10),engine="BLENDER_EEVEE")
except Exception as e:
    print("[transport] preview B failed:",e,flush=True)

all_objs=[]
for c in (MESH_COLL,COLL_COLL,LIGHT_COLL): all_objs.extend(list(c.objects))
obj_count=len(MESH_COLL.objects)+len(COLL_COLL.objects)+len(LIGHT_COLL.objects)
tri_expanded=ck.tri_count(MESH_COLL)+ck.tri_count(COLL_COLL)
tri_unique=ck.scene_tri_count()
per_fac=[]
for f in FACILITIES:
    fid=f["id"]; objs=FAC_OBJS.get(fid,[]); t=sum(ck.tri_count(o) for o in objs)
    per_fac.append({"id":fid,"objects":len(objs),"triangles":t,"rect":f["placement"].get("rect")})

report={
 "module":"transport",
 "blend":OUT_BLEND,
 "previews":[PREV_A,PREV_B],
 "collections":["Transport","Transport/Meshes","Transport/Colliders","Transport/Lights"],
 "objects":obj_count,
 "triangles_unique":tri_unique,
 "triangles_expanded":tri_expanded,
 "materials":sorted({mat.name for o in all_objs if getattr(o,"type",None)=="MESH" and getattr(o,"data",None) is not None for mat in o.data.materials}),
 "facilities":len(FACILITIES),
 "per_facility":per_fac,
 "lights":LIGHT_N[0],
 "collider_objects":len(COLL_COLL.objects),
 "build_seconds":round(time.time()-T0,1),
 "issues":[
  "No road geometry built by this module; entrances kept clear for Roads 8 m spurs.",
  "TRK_* facilities included per program owning_module=Transport; verify ownership with Track agent.",
 ],
 "needed_from_others":[
  "Roads: 8 m access spurs to each facility entrance; many band/outer sites have no adjacent road.",
  "Assembler: ground plane under outer frame and band lands.",
 ],
}
ck.write_report("transport",report)

lines=[]
lines.append("# Transport module report")
lines.append("")
lines.append("- blend: `%s`"%OUT_BLEND)
lines.append("- previews: `%s`, `%s`"%(PREV_A,PREV_B))
lines.append("- objects: %d"%obj_count)
lines.append("- triangles (unique/expanded): %d / %d"%(tri_unique,tri_expanded))
lines.append("- facilities: %d"%len(FACILITIES))
lines.append("- lights: %d"%LIGHT_N[0])
lines.append("")
lines.append("## Per facility")
lines.append("")
lines.append("| id | objects | triangles |")
lines.append("|---|---|---|")
for p in per_fac: lines.append("| %s | %d | %d |"%(p["id"],p["objects"],p["triangles"]))
lines.append("")
lines.append("## Materials")
lines.append("")
lines.append(", ".join(report["materials"]))
lines.append("")
lines.append("## Issues / needs")
lines.append("")
for i in report["issues"]+report["needed_from_others"]: lines.append("- "+i)
open(REPORT_MD,"w").write("\n".join(lines)+"\n")
print("[transport] DONE",obj_count,tri_expanded,flush=True)
