# FSmakeLobeHeadScrew.py  —  ASME B18.2.1.9  External 6-Lobe Bolt
# CSV: P, b, G, H, K, C, B, T, r1
# lobe_h = H-K  (lobes from flange face, slope T fills valleys inside)
#
# Thread types (UN standard):
#   UNC / UN  — flat root, straight line at minor dia (no arc)
#   UNR       — round root, arc r=0.3*P curves inward (clearly visible)
from screw_maker import *
_V=0.632; _RT=0.090

def _prism(G,h):
    A=G;V=G*_V;rt=G*_RT
    rv=-((V+sqrt3*(2*rt-A))*V+(A-4*rt)*A)/(4*V-2*sqrt3*A+(4*sqrt3-8)*rt)
    b=math.acos(max(-1.,min(1.,A/(4*rv+4*rt)-2*rt/(4*rv+4*rt))))-math.pi/6
    P0=Base.Vector(A/2-rt+rt*math.sin(b),-rt*math.cos(b),0)
    P1=Base.Vector(A/2,0,0)
    P2=Base.Vector(A/2-rt+rt*math.sin(b),rt*math.cos(b),0)
    Pi=Base.Vector(sqrt3*V/4,V/4,0)
    R=Base.Matrix();R.rotateZ(math.radians(60))
    e=[Part.Arc(P0,P1,P2).toShape()]
    Pi2=R.multiply(P0);e.append(Part.Arc(P2,Pi,Pi2).toShape())
    for i in range(5):
        P1=R.multiply(P1);P2=R.multiply(P2)
        e.append(Part.Arc(Pi2,P1,P2).toShape())
        Pi=R.multiply(Pi);Pi2=R.multiply(Pi2)
        e.append(Part.Arc(P2,Pi,P0 if i==4 else Pi2).toShape())
    return Part.Face(Part.Wire(e)).extrude(Base.Vector(0,0,h))


def _makeUNThreadCutter(dia, P, blen, unr=False):
    """
    UN / UNC / UNR external thread cutter.
    unr=False → FLAT root (UNC/UN):   straight line across root — no arc
    unr=True  → ROUND root (UNR):     mandatory arc, radius = 0.125*P

    ASME B1.1 profile (60° thread):
      H = P*sqrt(3)/2   (fundamental triangle height)
      Crest: truncated flat, width = P/8 each side
      Root:
        UNC/UN → flat at minor dia (dia/2 - 0.625*H), width = P/4
        UNR    → rounded arc tangent to flanks, r = 0.125*P
    """
    H  = sqrt3 / 2 * P
    d2 = dia / 2
    trot = blen // P + 1
    ht   = trot * P

    # Root zone dimensions
    x_root = d2 - 0.625 * H    # minor radius (flat bottom of thread)
    h_root = P / 8              # half-width of root (P/4 total flat width)

    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(d2 + sqrt3*3/80*P,  -0.475*P)    # crest bottom
    fm.AddPoint(x_root,             -h_root)      # root: left flank end
    if unr:
        # UNR — same pattern as existing CreateBlindThreadCutter but
        # with larger fillet radius (0.125*P vs sqrt3/12*P for UNC)
        # mid_x = x_root - 0.5*r  (same formula as WB standard cutter)
        r_unr  = 0.125 * P                             # UNR fillet radius
        fm.AddArc(x_root - 0.5*r_unr, 0, x_root, h_root)  # gentle rounded root
    else:
        # UNC/UN — flat root, straight horizontal line across bottom
        fm.AddPoint(x_root,          h_root)      # root: right flank end (flat)
    fm.AddPoint(d2 + sqrt3*3/80*P,  0.475*P)     # crest top
    wire = fm.GetClosedWire()
    wire.translate(Base.Vector(0, 0, -ht - P*0.6))

    # Lead helix radius — based on thread depth (same for UNC and UNR)
    thread_depth = 0.625 * H   # depth from major dia to minor dia
    helix      = Part.makeLongHelix(P, ht, dia/2, 0, False)
    lead_helix = Part.makeLongHelix(P, P/2, dia/2 + 0.55*thread_depth, 0, False)
    helix.rotate(Base.Vector(0,0,0), Base.Vector(1,0,0), 180)
    lead_helix.translate(Base.Vector(-0.55*thread_depth, 0, 0))

    path  = Part.Wire([helix, lead_helix])
    sweep = Part.BRepOffsetAPI.MakePipeShell(path)
    sweep.setFrenetMode(True)
    sweep.setTransitionMode(1)
    sweep.add(wire)
    if sweep.isReady():
        sweep.build()
    else:
        raise RuntimeError("UNR thread sweep failed")
    sweep.makeSolid()
    threads = sweep.shape()
    box = Part.makeBox(2*dia, 2*dia, dia, Base.Vector(-dia, -dia, -P*0.1))
    return threads.cut(box)


def makeLobeHeadScrew(self, fa):
    P,b,G,H,K,C,B,T,r1=fa.dimTable
    dia=self.getDia(fa.calc_diam,False)
    L=float(fa.calc_len) if fa.calc_len else 50.0

    # Thread pitch: ASME TPI or metric pitch
    tpi=getattr(fa,"calc_tpi",None)
    if tpi and tpi>0:
        P=25.4/tpi; td=dia-0.15/tpi
    else:
        rp=getattr(fa,"calc_pitch",None)
        if rp and rp>0: P=rp
        td=dia-0.15*P
    tr=td/2

    # Thread length override
    tl_ov=getattr(fa,"calc_thread_length",None) or 0
    if tl_ov>0: b=min(float(tl_ov),L)

    # ── ThreadType: read from fa (backed up by FastenersCmd BackupObject)
    # FastenersCmd stores fa.ThreadType via FastenerAttribs + BackupObject.
    # Priority: fa.ThreadType (from dashboard) → default "UNC"
    thread_type = getattr(fa, "ThreadType", "UNC") or "UNC"
    is_unr = (str(thread_type) == "UNR")

    c=max(K,.3); r=max(r1,.1)
    lh=H-K; vr=G*_V/2; rf=max(G*.04,.1)

    # Lobe head: z=c to z=c+lh
    f=FSFaceMaker()
    f.AddPoint(0,c+lh); f.AddPoint(G/2-rf,c+lh)
    f.AddArc2(0,-rf,-90)
    f.AddPoint(G/2,c); f.AddPoint(0,c)
    p=_prism(G,lh); p.translate(Base.Vector(0,0,c))
    head=self.RevolveZ(f.GetFace()).common(p)

    # Slope cone inside lobe zone: z=c to z=c+T
    f2=FSFaceMaker()
    f2.AddPoint(0,c+T); f2.AddPoint(vr,c+T)
    f2.AddPoint(G/2,c); f2.AddPoint(0,c)
    slope=self.RevolveZ(f2.GetFace())

    # Flange + shank: z=-L to z=c
    f.Reset()
    f.AddPoint(0,c); f.AddPoint(C/2-c/4,c)
    f.AddArc2(0,-c/4,-90)
    f.AddPoint(C/2,0); f.AddPoint(dia/2+r,0)
    f.AddArc2(0,-r,90); f.AddPoint(tr,-r)
    if L-r>b: tl=b; f.AddPoint(tr,-(L-b)) if not fa.Thread else None
    else: tl=L-r
    f.AddPoint(tr,-L+dia/10); f.AddPoint(dia*.4,-L); f.AddPoint(0,-L)
    shape=self.RevolveZ(f.GetFace()).fuse(slope).fuse(head)

    # Thread cut — UNC/UN (flat root) or UNR (round root)
    if fa.Thread:
        tc=_makeUNThreadCutter(td, P, tl, unr=is_unr)
        tc.translate(Base.Vector(0,0,-(L-tl)))
        shape=shape.cut(tc)
    return shape