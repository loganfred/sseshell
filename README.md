# sseshell

`sseshell` (pronounced like "seashell") is a barebones utility that creates a webpage to launch one or more shell commands with live updates from `stdout` and `stderr`.

## what problem does this solve?

Slapping a web ui around a collection of shell scripts:

+ helps you remember all these shell scripts exist
+ makes it easy to run them from other devices
+ enables non-technical people to run your scripts

It was inspired by [shell2http](https://github.com/msoap/shell2http), but purpose-built to stream output from long-running scripts.

## quick start

After cloning:

```sh
# cd sseshell
$ pip install aiohttp
$ echo 'for i in $(seq 1 10); do echo "Hello World $i"; sleep 1; done' >
commands.txt
$ python main.py
```

Now head to `localhost:8080` and click one of the run buttons.

## design philosophy and feature roadmap

This tool is deliberately as simplistic and ascetic as possible. It is a single Python file spanning less than 250 lines. It only requires `aiohttp`.

The simplicity makes it easy to audit for anyone curious about how it works or nervous about arbitrary remote code execution. The lack of screenshots, CSS, or other frills will hopefully dissuade adoption by unscrupulous users. It also helps to keep things as simple as possible because concurrency in general is nontrivial to reason about.

That said, here is the overhead on the roadmap:

1. a programmatic API, which will involve some task status endpoints
2. a mechanism for passing arguments to scripts which will require thinking about sanitization
3. support for halting a subprocess (for example, infinitely tailing a log file)
4. handling of ansi escape sequences like those used for in-place progress output

## documentation

The system uses an enumerated `cmd_id` to track each available command. This is better than permitting the user to execute arbitrary commands.

Requests to `/execute?cmd_idx=<cmd_id>` will do the following:

1. Generate a `task_id` which will be returned to the client in the response
2. Create an async queue registered to this `task_id` in the global task dictionary
3. Spawn an async routine that will run the command and shovel its output to the queue

`/stream/<task_id>` will pop the queue with MIME type `text/event-stream` so that AJAX can register a handler to update the page.
