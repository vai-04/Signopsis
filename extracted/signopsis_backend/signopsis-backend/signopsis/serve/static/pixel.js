// SIGNOPSIS pixel avatar renderer (shared by the text->sign and sign->text pages).
// Draws one frame of avatar2d.frames_json() onto a 100x100 canvas.
/* ------------------------------------------------------------------ pixel renderer */
const FALLBACK = {"--stage":"#1d2b3a","--stage2":"#223447","--body":"#3d5a80","--skinR":"#f2c29b",
  "--skinL":"#d9a47c","--back":"#b98460","--tip":"#fff1e0"};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || FALLBACK[n];
function px(ctx, x, y, s=1){ ctx.fillRect(Math.round(x), Math.round(y), s, s); }
function line(ctx, x0, y0, x1, y1, s=1){
  x0=Math.round(x0); y0=Math.round(y0); x1=Math.round(x1); y1=Math.round(y1);
  const dx=Math.abs(x1-x0), dy=-Math.abs(y1-y0), sx=x0<x1?1:-1, sy=y0<y1?1:-1; let e=dx+dy;
  for(;;){ ctx.fillRect(x0 - (s>1?1:0), y0 - (s>1?1:0), s, s); if(x0===x1&&y0===y1)break;
    const e2=2*e; if(e2>=dy){e+=dy;x0+=sx;} if(e2<=dx){e+=dx;y0+=sy;} }
}
function poly(ctx, pts){
  const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]);
  for(let y=Math.floor(Math.min(...ys)); y<=Math.ceil(Math.max(...ys)); y++){
    for(let x=Math.floor(Math.min(...xs)); x<=Math.ceil(Math.max(...xs)); x++){
      let inside=false;
      for(let i=0,j=pts.length-1;i<pts.length;j=i++){
        const [xi,yi]=pts[i],[xj,yj]=pts[j];
        if(((yi>y+.5)!==(yj>y+.5)) && (x+.5 < (xj-xi)*(y+.5-yi)/(yj-yi)+xi)) inside=!inside;
      }
      if(inside) ctx.fillRect(x,y,1,1);
    }
  }
}
const FINGERS=[[1,2,3,4],[5,6,7,8],[9,10,11,12],[13,14,15,16],[17,18,19,20]];

function drawHand(ctx, H, palm, skin, debug){
  const back = palm < 0;
  ctx.fillStyle = back ? css("--back") : skin;
  poly(ctx, [H[0], H[1], H[5], H[9], H[13], H[17]]);
  for (const f of FINGERS){
    ctx.fillStyle = back ? css("--back") : skin;
    line(ctx, ...H[f[0]===1?0:f[0]], ...H[f[0]], 2);
    for (let k=0;k<3;k++) line(ctx, ...H[f[k]], ...H[f[k+1]], 2);
    ctx.fillStyle = css("--tip"); px(ctx, ...H[f[3]]);
  }
  if (debug){ ctx.fillStyle = "#ff3df2"; for (const p of H) px(ctx, ...p); }
}

function drawBody(ctx, face){
  const hx = face.hx||0, hy = face.hy||0;
  ctx.fillStyle = css("--stage"); ctx.fillRect(0,0,100,100);
  ctx.fillStyle = css("--stage2"); for (let y=0;y<100;y+=4) ctx.fillRect(0,y,100,1);
  // torso + neck
  ctx.fillStyle = css("--body");
  poly(ctx, [[30,44],[70,44],[76,100],[24,100]]);
  ctx.fillRect(46,32,8,13);
  // head
  ctx.fillStyle = css("--skinR");
  const cx = 50+hx, cy = 22+hy;
  for (let y=-10;y<=10;y++) for (let x=-8;x<=8;x++) if ((x*x)/64+(y*y)/100<=1) ctx.fillRect(Math.round(cx+x),Math.round(cy+y),1,1);
  ctx.fillStyle = "#2b2b2b";          // hair
  for (let x=-8;x<=8;x++) for (let y=-10;y<=-6;y++) if ((x*x)/64+(y*y)/100<=1) ctx.fillRect(Math.round(cx+x),Math.round(cy+y),1,1);
  // eyes
  ctx.fillStyle = "#1a1a1a"; px(ctx,cx-4,cy-1,2); px(ctx,cx+3,cy-1,2);
  // brows: the question grammar lives here
  ctx.fillStyle = "#3a2a20";
  const b = face.brow;
  if (b==="raised"){ line(ctx,cx-5,cy-5,cx-2,cy-5); line(ctx,cx+2,cy-5,cx+5,cy-5); }
  else if (b==="furrowed"){ line(ctx,cx-5,cy-4,cx-2,cy-2); line(ctx,cx+2,cy-2,cx+5,cy-4); }
  else { line(ctx,cx-5,cy-3,cx-2,cy-3); line(ctx,cx+2,cy-3,cx+5,cy-3); }
  // mouth
  ctx.fillStyle = "#8a3b3b";
  if (face.mouth==="open") ctx.fillRect(Math.round(cx-2),Math.round(cy+4),4,3);
  else line(ctx,cx-2,cy+5,cx+2,cy+5);
}

function drawFrame(ctx, f, opts={}){
  drawBody(ctx, f.face || {});
  if (opts.trail && opts.frames){
    ctx.fillStyle = "#ffd48a55";
    const i = opts.index;
    for (let k=Math.max(0,i-12); k<i; k++){ const g=opts.frames[k]; px(ctx, ...g.R[8]); px(ctx, ...g.L[8]); }
  }
  // draw the hand that is further "back" first: left (non-dominant) then right
  drawHand(ctx, f.L, f.Lp, css("--skinL"), opts.debug);
  drawHand(ctx, f.R, f.Rp, css("--skinR"), opts.debug);
}


export { drawFrame, drawBody, drawHand, line, px };
