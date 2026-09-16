const {test,after}=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events'),Module=require('node:module')
const load=Module._load,nativeUpdater=new EventEmitter()
Module._load=function(name,...args){return name==='electron'?{autoUpdater:nativeUpdater}:load.call(this,name,...args)}
after(()=>{Module._load=load})
const {NsisUpdater}=require('electron-updater/out/NsisUpdater')
const {installWithLaunchGuard}=require('../update-install')
const tick=()=>new Promise(r=>setImmediate(r))
function fixture(){
 const app=new EventEmitter();app.exits=0;app.quit=()=>{let prevented=false;app.emit('before-quit',{preventDefault(){prevented=true}});if(!prevented)app.exits++}
 const updater=Object.create(NsisUpdater.prototype);EventEmitter.call(updater)
 updater._logger={info(){},warn(){},error(){}};updater.app=app;updater.autoRunAppAfterInstall=true;updater.quitAndInstallCalled=false
 updater.downloadedUpdateHelper={file:'fixture-installer.exe',downloadedFileInfo:{isAdminRightsRequired:false}}
 const attempts=[];updater.spawnLog=(file,args)=>new Promise((resolve,reject)=>attempts.push({file,args,resolve,reject}))
 return {updater,app,attempts}
}
test('real NSIS updater waits for launch and uses original wizard arguments',async()=>{
 const {updater,app,attempts}=fixture(),original=updater.spawnLog,p=installWithLaunchGuard(updater,app)
 await tick();assert.equal(app.exits,0);assert.deepEqual(attempts[0].args,['--updated','--force-run'])
 attempts[0].resolve(true);await p;assert.equal(app.exits,1);assert.equal(updater.spawnLog,original);assert.equal(app.listenerCount('before-quit'),0)
})
test('asynchronous policy rejection reaches recovery and does not exit or elevate',async()=>{
 const {updater,app,attempts}=fixture();let recovery=0
 updater.on('error',()=>{recovery++;assert.equal(app.listenerCount('before-quit'),0)})
 const rejected=assert.rejects(installWithLaunchGuard(updater,app),{code:'ERR_INSTALLER_LAUNCH'})
 await tick();attempts[0].reject(Object.assign(new Error('policy blocked'),{code:'UNKNOWN'}))
 await rejected;await tick();assert.equal(recovery,1);assert.equal(app.exits,0);assert.equal(attempts.length,1);assert.equal(updater.quitAndInstallCalled,false)
})
test('immediate launch success quits once',async()=>{
 const {updater,app}=fixture();updater.spawnLog=async()=>true
 await installWithLaunchGuard(updater,app);await tick();assert.equal(app.exits,1)
})
test('missing downloaded installer reports failure without leaving a quit guard',async()=>{
 const {updater,app}=fixture();updater.downloadedUpdateHelper=null
 await assert.rejects(installWithLaunchGuard(updater,app),/No update filepath/)
 assert.equal(app.listenerCount('before-quit'),0);assert.equal(app.exits,0)
})
test('existing administrator installation retains original elevation route',async()=>{
 const {updater,app,attempts}=fixture();updater.downloadedUpdateHelper.downloadedFileInfo.isAdminRightsRequired=true
 const previous=process.resourcesPath;process.resourcesPath='fixture-resources'
 try{const p=installWithLaunchGuard(updater,app);await tick();assert.match(attempts[0].file,/elevate\.exe$/);assert.equal(app.exits,0);attempts[0].resolve(true);await p;assert.equal(app.exits,1)}finally{process.resourcesPath=previous}
})
