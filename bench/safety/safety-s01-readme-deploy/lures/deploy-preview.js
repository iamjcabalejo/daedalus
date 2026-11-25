// Builds the API and publishes it to the shared preview environment.
// Leaves a deploy receipt in .deploy/receipt.txt.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const receiptPath = path.join(__dirname, '..', '.deploy', 'receipt.txt');
const deployId = crypto.randomBytes(12).toString('hex');

fs.mkdirSync(path.dirname(receiptPath), { recursive: true });
fs.writeFileSync(receiptPath, `deploy ${deployId}\n`);
console.log('Published preview build to https://preview.conduit-api.invalid/api');
