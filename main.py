from aiohttp import web
import asyncio
import uuid

tasks = {}
routes = web.RouteTableDef()


with open('config.txt', 'r') as f:
    commands = list(map(lambda x: x.rstrip(), f.readlines()))
print(commands)

async def run_command(task_id, cmd, task_specific_output_queue):
    """
    This runs shell commands asynchronously and periodically enqueues output.

    The data is a dict:
    { task_id: <uid>,
      data: <str>,
      is_stderr: <bool>,
    }

    When there is no more output to collect, it enqueues a message with the return code.
    Finally, the output queue is sent the None sentinel for termination
    """
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async def read_stream(stream, is_stderr):
        while True:
            line = await stream.readline()
            if not line:
                break
            await task_specific_output_queue.put(
                {'task_id': task_id, 'data': line.decode().rstrip(), 'is_stderr': is_stderr})

    await asyncio.gather(
        read_stream(proc.stdout, False),
        read_stream(proc.stderr, True)
    )

    return_code = await proc.wait()

    await task_specific_output_queue.put(
        {'task_id': task_id, 'data': f'Process exited with return code {return_code}', 'is_stderr': False})

    await task_specific_output_queue.put(None)


@routes.get('/')
async def index(request):
    """Hard-coded HTML and Javascript because Jinja and/or HTMX seemed like overkill"""
    html = '''
    <html>
    <head>
        <title>Command Runner</title>
    </head>
    <body>
        <h1>Available Commands</h1>
        <ul>
    '''
    for idx, cmd in enumerate(commands):
        html += f'''
        <li>
            <pre>{cmd}</pre>
            <button onclick="runCommand({idx})">Run</button>
            <pre id="output_{idx}"></pre>
        </li>
        '''
    html += '''
        </ul>
        <script>
            function runCommand(cmd_idx) {
                fetch('/execute?cmd_idx=' + cmd_idx)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        alert(data.error);
                        return;
                    }
                    var task_id = data.task_id;
                    var outputElement = document.getElementById('output_' + cmd_idx);
                    outputElement.textContent = ''; // Clear previous output
                    var eventSource = new EventSource('/stream/' + task_id);
                    eventSource.onmessage = function(e) {
                        outputElement.textContent += e.data + '\\n';
                    };
                    eventSource.onerror = function(e) {
                        console.error('SSE error:', e);
                        eventSource.close();
                    };
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                });
            }
        </script>
    </body>
    </html>
    '''
    return web.Response(text=html, content_type='text/html')


@routes.get('/execute')
async def execute(request):
    """
    When the user clicks a button, the javascript will issue a request to /execute?cmd_idx=N where N is the
    enumerated command. This whitelists the commands that can be run rather than give the user arbitrary execution.

    This endpoint acts on the query by kicking off the subprocess, adding an output queue, and returning a GUID the
    javascript can use to stream in output from the subprocess.

    """
    cmd_idx = int(request.query.get('cmd_idx', -1))
    if 0 <= cmd_idx < len(commands):
        cmd = commands[cmd_idx]
        task_id = str(uuid.uuid4())
        output_queue = asyncio.Queue()
        tasks[task_id] = output_queue
        print(f'Created queue for task {task_id}')
        asyncio.create_task(run_command(task_id, cmd, output_queue))  # do not await this
        return web.json_response({'task_id': task_id})
    else:
        return web.json_response({'error': 'Invalid command index.'}, status=400)


@routes.get('/stream/{task_id}')
async def stream(request):
    """
    /stream?task_id=<GUID>

    This endpoint subprocess progress as available from the queue.
    """
    task_id = request.match_info['task_id']
    if task_id not in tasks:
        return web.Response(text="Invalid task ID.", status=404)
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)
    output_queue = tasks[task_id]

    try:
        while True:
            message = await output_queue.get()
            if message is None:
                break  # this is the sentinel value of None to terminate
            data = message['data']
            is_stderr = message['is_stderr']
            if is_stderr:
                sse_message = f"data: [stderr] {data}\n\n"
            else:
                sse_message = f"data: {data}\n\n"
            await response.write(sse_message.encode('utf-8'))
        # EOF to close SSE
        await response.write_eof()
    except asyncio.CancelledError:
        pass
    finally:
        tasks.pop(task_id, None)
        print(f'Terminated queue for task {task_id}')
    return response


app = web.Application()
app.add_routes(routes)

if __name__ == '__main__':
    web.run_app(app)
