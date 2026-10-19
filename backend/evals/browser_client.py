"""Opt-in real Chromium UI transport for the existing paired evaluator.

One UI submission is one inference. The browser tees the SAME SSE response to
measure network and rendered content; it never replays or duplicates a request.
"""
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time


class BrowserClient:
    def __init__(self, client, app, folder, budget, observe, model):
        from app.evaluation_budget import current_budget
        from app.model_runtime import request_observer
        import uvicorn
        root=Path(__file__).resolve().parents[2]
        self.client=client
        self.server=None
        self.process=None
        node=os.environ.get('CHONGBAN_TEST_NODE')
        if not node or not Path(node).is_file():
            raise ValueError('CHONGBAN_TEST_NODE must name the installed Node executable')
        # A frozen backend uses exactly the same current frontend build.
        if not any(getattr(route,'path',None)=='/' for route in app.routes):
            from app.main import SPAFiles
            app.mount('/',SPAFiles(directory=root/'frontend/dist',html=True),name='evaluation-frontend')
        with socket.socket() as bound:
            bound.bind(('127.0.0.1',0))
            port=bound.getsockname()[1]
        class BudgetApp:
            async def __call__(self,scope,receive,send):
                token=current_budget.set(budget)
                observation=request_observer.set(observe)
                try:
                    await app(scope,receive,send)
                finally:
                    request_observer.reset(observation)
                    current_budget.reset(token)
        self.server=uvicorn.Server(uvicorn.Config(BudgetApp(),host='127.0.0.1',port=port,
                                                log_level='error',lifespan='off'))
        self.thread=threading.Thread(target=self.server.run,daemon=True)
        self.thread.start()
        deadline=time.monotonic()+15
        while not self.server.started:
            if time.monotonic()>deadline:
                self.close()
                raise RuntimeError('Isolated browser server did not start')
            time.sleep(.025)
        env=dict(os.environ,EVAL_BROWSER_URL=f'http://127.0.0.1:{port}',
                 EVAL_BROWSER_MODEL='demo' if model=='demo' else 'deepseek' if model=='deepseek-flash' else 'alibaba',
                 EVAL_BROWSER_FOLDER=str(folder))
        self.stderr=(folder/'browser-stderr.log').open('w',encoding='utf-8')
        self.process=subprocess.Popen([node,str(Path(__file__).with_name('browser_worker.mjs'))],
            cwd=root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,
            text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        ready=json.loads(self.process.stdout.readline())
        if ready.get('event')!='ready':
            self.close()
            raise RuntimeError('Real browser initialization failed')

    def __getattr__(self,name):
        return getattr(self.client,name)

    def post(self,path,**kwargs):
        if path!='/api/v1/chat':
            return self.client.post(path,**kwargs)
        self.process.stdin.write(json.dumps({'payload':kwargs['json'],
            'key':kwargs.get('headers',{}).get('Idempotency-Key')},ensure_ascii=True)+'\n')
        self.process.stdin.flush()
        line=self.process.stdout.readline()
        if not line:
            raise RuntimeError('Browser worker exited without a result')
        data=json.loads(line)
        if data.get('event')!='result':
            raise RuntimeError('Browser evaluation failed without automatic retry')
        import httpx2
        return httpx2.Response(data['status'],json=data['result'],headers=data.get('headers',{}))

    def close(self):
        if self.process:
            with contextlib.suppress(OSError):
                self.process.stdin.close()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=8)
        if self.server:
            self.server.should_exit=True
            self.thread.join(timeout=5)
        if getattr(self,'stderr',None):
            self.stderr.close()
