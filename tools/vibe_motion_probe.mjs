// AlI feasibility adapter for vibe-motion-3d's deterministic frame contract.
// This experiment uses an actual Three.js Bone hierarchy; it is not a pose ControlNet.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {pathToFileURL} from 'node:url';

const [source,out,browserPath]=process.argv.slice(2);
if(!source||!out||!browserPath)throw Error('Expected Vibe template source, new output directory and Chromium path');
const template=path.join(source,'packages/template');
const {default:puppeteer}=await import(pathToFileURL(path.join(template,'node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js')).href);
const threeRoot=await fs.realpath(path.join(template,'node_modules/three'));
await fs.mkdir(out,{recursive:false});await fs.mkdir(path.join(out,'frames'));
const scene=String.raw`
import * as THREE from '/three/build/three.module.js';
const canvas=document.querySelector('canvas');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});renderer.setSize(512,768);renderer.setPixelRatio(1);
renderer.outputColorSpace=THREE.SRGBColorSpace;
const scene=new THREE.Scene();scene.background=new THREE.Color('#e8e8e8');
scene.add(new THREE.AmbientLight(0xffffff,2));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(3,5,4);scene.add(light);
const camera=new THREE.OrthographicCamera(-.95,.95,1.425,-1.425,.1,20);camera.position.set(0,1.1,6);camera.lookAt(0,1.1,0);
const mat=new THREE.MeshStandardMaterial({color:'#74869c',roughness:.8});const joints={};
function bone(name,parent,p){const b=new THREE.Bone();b.name=name;b.position.set(...p);parent.add(b);joints[name]=b;return b;}
function sphere(parent,r){const m=new THREE.Mesh(new THREE.SphereGeometry(r,20,12),mat);parent.add(m);return m;}
function limb(parent,end,r){const direction=new THREE.Vector3(...end);const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,direction.length(),12),mat);m.position.copy(direction).multiplyScalar(.5);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize());parent.add(m);}
const hips=bone('hips',scene,[0,.9,0]);sphere(hips,.16);
const spine=bone('spine',hips,[0,.34,0]);limb(hips,[0,.34,0],.17);
const chest=bone('chest',spine,[0,.31,0]);limb(spine,[0,.31,0],.21);
const head=bone('head',chest,[0,.28,0]);sphere(head,.22);
for(const side of [-1,1]){const prefix=side<0?'left':'right';
 const upper=bone(prefix+'UpperArm',chest,[side*.28,-.02,0]);sphere(upper,.095);limb(upper,[0,-.36,0],.075);
 const lower=bone(prefix+'Forearm',upper,[0,-.36,0]);sphere(lower,.08);limb(lower,[0,-.32,0],.065);
 const hand=bone(prefix+'Hand',lower,[0,-.32,0]);sphere(hand,.09);
 const thigh=bone(prefix+'Thigh',hips,[side*.13,-.07,0]);limb(thigh,[0,-.38,0],.09);
 const shin=bone(prefix+'Shin',thigh,[0,-.38,0]);sphere(shin,.08);limb(shin,[0,-.36,0],.075);sphere(bone(prefix+'Foot',shin,[0,-.36,.08]),.09);
}
const skeleton=new THREE.Skeleton(Object.values(joints));skeleton.calculateInverses();
function apply(frame){
 const t=frame/24;const phase=Math.sin(Math.min(1,t/.65)*Math.PI/2);const pulse=t<.65?0:Math.sin((t-.65)*Math.PI*4)*.06;
 for(const side of [-1,1]){const prefix=side<0?'left':'right';joints[prefix+'UpperArm'].rotation.z=side*(2.45*phase+pulse);joints[prefix+'Forearm'].rotation.z=side*2.0*phase;}
 hips.rotation.y=Math.sin(t*Math.PI*2)*.06*phase;renderer.render(scene,camera);
 return Object.fromEntries(['leftHand','rightHand','head'].map(n=>{const p=new THREE.Vector3();joints[n].getWorldPosition(p);return[n,p.toArray()];}));
}
window.__SCENE_3D_EXPORT__={isReady:()=>true,getCurrentFrame:()=>window.currentFrame||0,getTotalFrames:()=>48,getSize:()=>({width:512,height:768}),setFrame:f=>{window.currentFrame=f;return apply(f);}};
apply(0);
`;
await fs.writeFile(path.join(out,'scene.js'),scene);
const server=http.createServer(async(req,res)=>{
 try{
  if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<html><body style="margin:0"><canvas></canvas><script type="module" src="/scene.js"></script></body></html>');return;}
  let file=req.url==='/scene.js'?path.join(out,'scene.js'):req.url.startsWith('/three/')?path.join(threeRoot,req.url.slice(7)):null;
  if(!file||!path.resolve(file).startsWith(path.resolve(req.url==='/scene.js'?out:threeRoot)+path.sep))throw Error('Invalid path');
  res.setHeader('Content-Type','text/javascript');res.end(await fs.readFile(file));
 }catch(error){res.statusCode=404;res.end('Not found');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
try{
 browser=await puppeteer.launch({headless:true,executablePath:browserPath,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage();await page.setViewport({width:512,height:768,deviceScaleFactor:1});page.on('pageerror',error=>{console.error(error);});
 await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.__SCENE_3D_EXPORT__?.isReady(),{timeout:30000});
 const positions=[];
 for(let frame=0;frame<48;frame++){
  positions.push(await page.evaluate(f=>window.__SCENE_3D_EXPORT__.setFrame(f),frame));
  await page.screenshot({path:path.join(out,'frames','frame_'+String(frame).padStart(4,'0')+'.png')});
 }
 await page.evaluate(()=>window.__SCENE_3D_EXPORT__.setFrame(24));const twice=await page.screenshot();
 const deterministic=Buffer.compare(twice,await fs.readFile(path.join(out,'frames/frame_0024.png')))===0;
 if(!deterministic)throw Error('Random access rendering changed frame 24');
 await fs.writeFile(path.join(out,'frames/sprite_sheet.json'),JSON.stringify({fps:24},null,2));
 await fs.writeFile(path.join(out,'adapter-review.json'),JSON.stringify({source:'vibe-motion/create-vibe-motion-3d',upstreamCommit:'b88aa9999ab37b6202b5d7370a91e85ded0e1919',contract:'__SCENE_3D_EXPORT__',actualBoneHierarchy:true,rigidBoneAttachments:true,skinnedCharacter:false,frames:48,fps:24,randomAccessIdentical:deterministic,positions,poseControlCondition:false,normalUIEnabled:false},null,2));
 console.log('48 deterministic bone-controlled reference frames exported; H3 fidelity not yet verified');
}finally{if(browser)await browser.close();server.close();}
