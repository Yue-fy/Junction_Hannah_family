"""Run the dependency-free local S-Coach demo."""
import argparse
from pathlib import Path
from .api import Application, create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Serve the S-Coach local demo')
    root = Path(__file__).resolve().parent.parent
    parser.add_argument('--db', default=str(root / 'var' / 'scoach.sqlite3'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--web-root', default=str(root / 'web'))
    args = parser.parse_args(argv)
    server = create_server(Application(args.db, args.web_root), host=args.host, port=args.port)
    print(f'S-Coach: http://{args.host}:{server.server_address[1]}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
