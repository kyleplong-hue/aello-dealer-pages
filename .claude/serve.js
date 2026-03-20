const http = require('http');
const fs = require('fs');
const path = require('path');
const dir = path.join(__dirname, '..');
const server = http.createServer((req, res) => {
  const filePath = path.join(dir, req.url === '/' ? 'aello-dealer-landing.html' : req.url);
  const ext = path.extname(filePath);
  const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.gif': 'image/gif', '.jpg': 'image/jpeg' };
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    res.writeHead(200, { 'Content-Type': types[ext] || 'text/plain' });
    res.end(data);
  });
});
server.listen(3000, () => console.log('Serving on http://localhost:3000'));
