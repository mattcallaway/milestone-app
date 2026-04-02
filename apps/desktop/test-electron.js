try {
const electron = require('node:electron');
console.log('--- ELECTRON DEBUG START ---');
console.log('Type of require("node:electron"):', typeof electron);
console.log('Keys of require("node:electron"):', Object.keys(electron));
console.log('Versions:', process.versions);
console.log('--- ELECTRON DEBUG END ---');
if (electron.app) {
    console.log('Success: app exists via node:electron');
    process.exit(0);
} else {
    console.log('Failure: app is undefined via node:electron');
    process.exit(1);
}
} catch (e) {
    console.error('Error requiring node:electron:', e);
    process.exit(1);
}
