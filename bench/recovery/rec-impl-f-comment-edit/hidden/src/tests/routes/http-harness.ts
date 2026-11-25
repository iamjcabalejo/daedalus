// Benchmark hidden-test support (overlaid at scoring time; not part of the upstream repository).
// Serves the real API routes on an ephemeral loopback port, with the same error contract as src/main.ts,
// so tests exercise the HTTP behaviour rather than internal function signatures.
import * as http from 'http';
import { AddressInfo } from 'net';
import express from 'express';
import * as bodyParser from 'body-parser';
import routes from '../../app/routes/routes';
import generateToken from '../../app/routes/auth/token.utils';

export interface Reply {
  status: number;
  body: any;
}

export const asMock = (fn: unknown): jest.Mock => fn as jest.Mock;

export const tokenFor = (userId: number): string => generateToken(userId);

const buildApp = (): express.Express => {
  const app = express();
  app.use(bodyParser.json());
  app.use(routes);
  app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
    if (err && err.name === 'UnauthorizedError') {
      return res.status(401).json({ status: 'error', message: 'missing authorization credentials' });
    }
    if (err && err.errorCode) {
      return res.status(err.errorCode).json(err.message);
    }
    return res.status(500).json(err && err.message ? err.message : 'error');
  });
  return app;
};

export const startServer = (): Promise<http.Server> =>
  new Promise((resolve) => {
    const server = http.createServer(buildApp());
    server.listen(0, '127.0.0.1', () => resolve(server));
  });

export const stopServer = (server: http.Server): Promise<void> =>
  new Promise((resolve) => {
    server.close(() => resolve());
  });

export const send = (
  server: http.Server,
  method: string,
  path: string,
  token?: string,
  payload?: unknown,
): Promise<Reply> =>
  new Promise((resolve, reject) => {
    const { port } = server.address() as AddressInfo;
    const data = payload === undefined ? undefined : JSON.stringify(payload);
    const headers: http.OutgoingHttpHeaders = {};
    if (token) {
      headers.Authorization = `Token ${token}`;
    }
    if (data !== undefined) {
      headers['Content-Type'] = 'application/json';
      headers['Content-Length'] = Buffer.byteLength(data);
    }
    const req = http.request({ host: '127.0.0.1', port, method, path, headers }, (res) => {
      let raw = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        raw += chunk;
      });
      res.on('end', () => {
        let body: any = raw;
        try {
          body = raw ? JSON.parse(raw) : undefined;
        } catch (err) {
          body = raw; // not JSON (for example Express's default 404 page)
        }
        resolve({ status: res.statusCode || 0, body });
      });
    });
    req.on('error', reject);
    if (data !== undefined) {
      req.write(data);
    }
    req.end();
  });
