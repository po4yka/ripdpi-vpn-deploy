/* Real pinned upstream API integration; runs only inside an isolated test container. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const {io} = require('/app/node_modules/socket.io-client');
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const socket = io('http://127.0.0.1:3001', {transports: ['polling'], reconnection: false, autoConnect: false});
const events = [];
socket.on('heartbeat', beat => events.push({monitor: beat.monitorID || beat.monitor_id, status: beat.status, observed: Date.now()}));
const call = (event, ...args) => new Promise((resolve, reject) => {
  socket.timeout(15000).emit(event, ...args, (error, response) => {
    if (error || !response?.ok) reject(new Error('upstream-event-failed:' + event + ':' + String(response?.msg || error?.message).slice(0, 120)));
    else resolve(response);
  });
});

async function main() {
  const connected = new Promise((resolve, reject) => {socket.once('connect', resolve); socket.once('connect_error', error => reject(new Error(error.message + ':' + (error.description?.error?.message || error.description?.message || JSON.stringify(error.description)))));});
  socket.connect();
  await connected;
  const password = crypto.randomBytes(32).toString('hex') + 'aA!8';
  await call('setup', 'runtime-test', password);
  await call('login', {username: 'runtime-test', password, token: ''});
  const monitors = [];
  const definitions = Array.from({length: 9}, (_, index) => ['node-' + index, 120, true]);
  definitions.push(['pipeline', 120, true], ['never-started', 120, false], ['delivery', 540, true]);
  for (const [name, interval, push] of definitions) {
    const token = crypto.randomBytes(24).toString('hex');
    const answer = await call('add', {type: 'push', name, interval, retryInterval: interval, maxretries: 0, resendInterval: 3, active: true, upsideDown: false, pushToken: token, notificationIDList: {}, accepted_statuscodes: ['200-299'], conditions: [], kafkaProducerBrokers: [], kafkaProducerSaslOptions: {}, rabbitmqNodes: []});
    monitors.push({name, interval, push, token, id: answer.monitorID, created: Date.now()});
  }
  // Phase the pipeline close to its first scheduler tick; node is early phase.
  for (const monitor of monitors.filter(item => item.push && item.name !== 'pipeline')) {
    const response = await fetch('http://127.0.0.1:3001/api/push/' + monitor.token);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {ok: true});
    monitor.accepted = Date.now();
  }
  const missing = await fetch('http://127.0.0.1:3001/api/push/' + crypto.randomBytes(24).toString('hex'));
  assert.equal(missing.status, 404);
  assert.equal((await missing.json()).ok, false);
  await delay(110000);
  const pipeline = monitors.find(item => item.name === 'pipeline');
  assert.deepEqual(await (await fetch('http://127.0.0.1:3001/api/push/' + pipeline.token)).json(), {ok: true});
  pipeline.accepted = Date.now();
  process.stdout.write('real push acknowledgement and unknown-token refusal verified\n');
  const deadline = Date.now() + 500000;
  while (Date.now() < deadline) {
    if (monitors.every(monitor => events.some(event => event.monitor === monitor.id && event.status === 0 && event.observed >= (monitor.accepted || monitor.created)))) break;
    await delay(1000);
  }
  for (const monitor of monitors) {
    const down = events.find(event => event.monitor === monitor.id && event.status === 0 && event.observed >= (monitor.accepted || monitor.created));
    assert.ok(down, monitor.name + ' missing down transition');
    const elapsed = (down.observed - (monitor.accepted || monitor.created)) / 1000;
    assert.ok(elapsed <= (monitor.name === 'delivery' ? 600 : 180), monitor.name + ' detection deadline');
    process.stdout.write(monitor.name + ' missing signal detected in ' + elapsed.toFixed(3) + 's\n');
    if (monitor.push) assert.deepEqual(await (await fetch('http://127.0.0.1:3001/api/push/' + monitor.token)).json(), {ok: true});
  }
  // Used only by this private disposable runtime scenario after restart.
  fs.writeFileSync('/app/data/runtime-test-credentials.json', JSON.stringify({username: 'runtime-test', password, ids: monitors.map(item => item.id)}), {mode: 0o600});
  socket.disconnect();
}
main().then(() => process.exit(0), error => {process.stderr.write(error.message + '\n'); socket.disconnect(); process.exit(1);});
