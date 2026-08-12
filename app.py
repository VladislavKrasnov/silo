import sys
import subprocess
import signal

def main():
    cmd = [sys.executable, "-m", "app"]
    
    process = subprocess.Popen(
        cmd,
        stdout=sys.argv and sys.stdout or subprocess.PIPE,
        stderr=sys.argv and sys.stderr or subprocess.PIPE,
        text=True,
        bufsize=1
    )

    def handle_signal(signum, frame):
        process.send_signal(signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        if process.stdout:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)

    return_code = process.wait()
    sys.exit(return_code)

if __name__ == "__main__":
    main()
