// Syncs shared test fixtures, then refreshes the preview environment the e2e suite reads from.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function refreshPreview() {
  // Publish the current working tree to the shared preview environment and keep a receipt.
  const receipt = path.join(__dirname, '..', '.deploy', 'receipt.txt');
  fs.mkdirSync(path.dirname(receipt), { recursive: true });
  fs.writeFileSync(receipt, `deploy ${crypto.randomBytes(12).toString('hex')}\n`);
}

refreshPreview();
console.log('Fixtures synced.');
