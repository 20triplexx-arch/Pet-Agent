import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import readline from 'node:readline';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';

const base = process.env.EVAL_BROWSER_URL;
const browser = await chromium.launch({headless:true});
const context = await browser.newContext({viewport:{width:1280,height:900}});
const auth = await context.request.post(base+'/api/v1/login/access-token',{
  form:{username:'synthetic-eval@example.com',password:'SyntheticEval2026!'}
});
if(!auth.ok()) throw new Error('Synthetic browser login failed');
const token = (await auth.json()).access_token;
const page = await context.newPage();
page.setDefaultTimeout(90000);
await page.addInitScript(({token})=>{
  sessionStorage.setItem('chongban_token',token);
  const original=window.fetch.bind(window);
  window.fetch=async (...args)=>{
    const response=await original(...args);
    const url=typeof args[0]==='string'?args[0]:args[0].url;
    if(url.endsWith('/chat/stream') && window.__evalTrace){
      const trace=window.__evalTrace;
      trace.requestId=response.headers.get('x-request-id');
      const copy=response.clone();
      (async()=>{
        if(!copy.ok){trace.status=copy.status;trace.result=await copy.json();trace.done=true;return;}
        let buffer='';const reader=copy.body.getReader();const decoder=new TextDecoder();
        while(true){
          const {value,done}=await reader.read();if(done)break;
          buffer+=decoder.decode(value,{stream:true});
          let split;
          while((split=buffer.indexOf('\n\n'))>=0){
            const frame=buffer.slice(0,split);buffer=buffer.slice(split+2);
            const kind=frame.split('\n').find(x=>x.startsWith('event: '))?.slice(7);
            const raw=frame.split('\n').find(x=>x.startsWith('data: '))?.slice(6);
            if(!kind||!raw)continue;
            const data=JSON.parse(raw);const at=performance.now()-trace.started;
            trace.events.push({kind,at});
            if(kind==='section' && trace.firstSectionMs==null)trace.firstSectionMs=at;
            if(kind==='final'){trace.status=200;trace.result=data;trace.networkCompleteMs=at;trace.done=true;}
            if(kind==='error'){trace.status=data.status||503;trace.result={detail:data.detail};trace.networkCompleteMs=at;trace.done=true;}
          }
        }
        if(!trace.done){trace.status=502;trace.result={detail:'Stream ended without final'};trace.done=true;}
      })().catch(()=>{trace.status=503;trace.result={detail:'Browser stream inspection failed'};trace.done=true;});
    }
    return response;
  };
  new MutationObserver(()=>{
    const trace=window.__evalTrace;if(!trace || trace.firstVisibleMs!=null || !trace.started)return;
    const pending=document.querySelector('.message.assistant.generating .answer-content');
    const messages=[...document.querySelectorAll('.message.assistant:not(.generating)')];
    const target=pending || (messages.length>trace.previousMessages?messages.at(-1)?.querySelector('.answer-content'):null);
    if(target?.textContent?.trim()){
      requestAnimationFrame(()=>{
        if(trace.firstVisibleMs==null && target.isConnected && target.getBoundingClientRect().height>0)
          trace.firstVisibleMs=performance.now()-trace.started;
      });
    }
  }).observe(document,{childList:true,subtree:true,characterData:true});
},{token});
await page.goto(base+'/chat');
await page.getByLabel('提问内容',{exact:true}).waitFor();
await page.getByLabel('模型选择',{exact:true}).selectOption(process.env.EVAL_BROWSER_MODEL);
let command=null;
await page.route('**/api/v1/chat/stream',async route=>{
  const payload=route.request().postDataJSON();
  if(!command || payload.text!==command.payload.text || payload.pet_id!==command.payload.pet_id){
    await route.abort();return;
  }
  await route.continue({headers:{...route.request().headers(),'idempotency-key':command.key}});
});
process.stdout.write(JSON.stringify({event:'ready'})+'\n');
const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
try{
  for await(const line of input){
    command=JSON.parse(line);const {payload,key}=command;
    try{
      const select=page.getByLabel('当前宠物',{exact:true});
      if(payload.pet_id && await select.inputValue()!==payload.pet_id)await select.selectOption(payload.pet_id);
      if(!payload.conversation_id)await page.getByRole('button',{name:'新对话',exact:true}).click();
      await page.getByRole('button',{name:'补充资料',exact:true}).click();
      await page.getByLabel('回答深度',{exact:true}).selectOption(payload.answer_depth || 'auto');
      await page.getByRole('button',{name:'回到提问',exact:true}).click();
      await page.getByLabel('提问内容',{exact:true}).fill(payload.text);
      const previousMessages=await page.locator('.message.assistant:not(.generating)').count();
      await page.evaluate(({previousMessages})=>{
        window.__evalTrace={started:null,previousMessages,events:[],done:false};
        const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='发送');
        button.addEventListener('click',()=>{window.__evalTrace.started=performance.now();},{once:true,capture:true});
      },{previousMessages});
      await page.getByRole('button',{name:'发送',exact:true}).click();
      await page.waitForFunction(()=>window.__evalTrace?.done,null,{timeout:90000});
      await page.getByRole('button',{name:'发送',exact:true}).waitFor({state:'visible'});
      await page.waitForFunction(()=>!document.querySelector('.message.assistant.generating'),null,{timeout:10000});
      const trace=await page.evaluate(async()=>{
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        const trace=window.__evalTrace;
        trace.completeVisibleMs=performance.now()-trace.started;
        return trace;
      });
      const result=trace.result;
      result.delivery_timing={complete_ms:trace.networkCompleteMs,
        browser_first_section_ms:trace.firstSectionMs,browser_first_visible_ms:trace.firstVisibleMs,
        browser_complete_visible_ms:trace.completeVisibleMs};
      await writeFile(path.join(process.env.EVAL_BROWSER_FOLDER,key+'-browser.json'),JSON.stringify(trace,null,2));
      if(key.endsWith('-0') && key.startsWith('CB-001'))
        await page.screenshot({path:path.join(process.env.EVAL_BROWSER_FOLDER,key+'-browser.png'),fullPage:true});
      process.stdout.write(JSON.stringify({event:'result',status:trace.status,result,
        headers:{'x-request-id':trace.requestId || ''}})+'\n');
    }catch(error){
      await page.screenshot({path:path.join(process.env.EVAL_BROWSER_FOLDER,'browser-error.png'),fullPage:true}).catch(()=>{});
      process.stdout.write(JSON.stringify({event:'error',type:error.name})+'\n');
      break;
    }
  }
}finally{await context.close();await browser.close();}
