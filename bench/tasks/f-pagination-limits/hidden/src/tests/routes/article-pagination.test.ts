import * as http from 'http';
import prismaMock from '../prisma-mock';
import { asMock, send, startServer, stopServer, tokenFor } from './http-harness';

// The page size and offset actually requested from the database for the most recent list query.
const lastPage = (): { take: unknown; skip: unknown } => {
  const calls = asMock(prismaMock.article.findMany).mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  const args = calls[calls.length - 1][0] || {};
  return { take: args.take, skip: args.skip };
};

describe('article list paging limits', () => {
  let server: http.Server;

  beforeAll(async () => {
    server = await startServer();
  });

  afterAll(async () => {
    await stopServer(server);
  });

  beforeEach(() => {
    asMock(prismaMock.article.count).mockResolvedValue(0);
    asMock(prismaMock.article.findMany).mockResolvedValue([]);
    asMock(prismaMock.$transaction).mockImplementation(async (arg: any) =>
      Array.isArray(arg) ? Promise.all(arg) : arg(prismaMock),
    );
  });

  test.each([
    ['limit=500&offset=-3', 100, 0],
    ['limit=101&offset=0', 100, 0],
    ['limit=100&offset=200', 100, 200],
    ['limit=25&offset=50', 25, 50],
    ['limit=1', 1, 0],
    ['', 10, 0],
    ['limit=abc&offset=xyz', 10, 0],
    ['limit=0', 10, 0],
    ['limit=-5&offset=-1', 10, 0],
    ['limit=2.5&offset=1.5', 10, 0],
  ])('GET /api/articles?%s asks for take=%d, skip=%d', async (query, take, skip) => {
    const reply = await send(server, 'GET', `/api/articles${query ? `?${query}` : ''}`);
    expect(reply.status).toBe(200);
    expect(lastPage()).toEqual({ take, skip });
  });

  test('the list response keeps its shape', async () => {
    const reply = await send(server, 'GET', '/api/articles?limit=500');
    expect(reply.status).toBe(200);
    expect(reply.body).toEqual({ articles: [], articlesCount: 0 });
  });

  test.each([
    ['limit=1000&offset=-1', 100, 0],
    ['limit=5&offset=10', 5, 10],
    ['', 10, 0],
    ['limit=nope&offset=-20', 10, 0],
    ['limit=3.7', 10, 0],
  ])('GET /api/articles/feed?%s asks for take=%d, skip=%d', async (query, take, skip) => {
    const reply = await send(server, 'GET', `/api/articles/feed${query ? `?${query}` : ''}`, tokenFor(1));
    expect(reply.status).toBe(200);
    expect(lastPage()).toEqual({ take, skip });
  });
});
