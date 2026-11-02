"use strict";

// Run against the built image, with no external network or production data.
const assert = require("node:assert/strict");
const { createRequire } = require("node:module");
const net = require("node:net");
const { once } = require("node:events");
const app = createRequire("/app/package.json");
const { RedBeanNode } = app("redbean-node");
const knex = app("knex");
const Dialect = app("knex/lib/dialects/sqlite3/index.js");
const { MqttMonitorType } = app("./server/monitor-types/mqtt");
const packet = createRequire(app.resolve("mqtt"))("mqtt-packet");

async function sqliteAndModels() {
    assert.throws(() => app.resolve("node-gyp"), { code: "MODULE_NOT_FOUND" });
    // Use the same native driver selection as Kuma's Database.connect.
    Dialect.prototype._driver = () => app("@louislam/sqlite3");
    const db = new RedBeanNode();
    db.setup(knex({ client: Dialect, connection: { filename: ":memory:" },
        useNullAsDefault: true, pool: { min: 1, max: 1 } }));
    try {
        db.autoloadModels("/app/server/model", "js");
        assert.equal(typeof db.modelList.monitor, "function");
        assert.equal(typeof db.modelList.user, "function");
        const row = db.dispense("security_probe");
        row.label = "native-sqlite-readback";
        const id = await db.store(row);
        assert.ok(id > 0);
        assert.equal((await db.load("security_probe", id)).label, "native-sqlite-readback");
        assert.equal((await db.knex.raw("PRAGMA quick_check"))[0].quick_check, "ok");
    } finally {
        await db.close();
    }
}

async function mqttConsumer() {
    const sockets = new Set();
    const seen = [];
    let wireFailure;
    const broker = net.createServer((socket) => {
        sockets.add(socket);
        socket.on("close", () => sockets.delete(socket));
        socket.on("error", (error) => { wireFailure = error; });
        const parser = packet.parser();
        parser.on("error", (error) => { wireFailure = error; socket.destroy(); });
        socket.on("data", (bytes) => parser.parse(bytes));
        parser.on("packet", (message) => {
            try {
                seen.push(message.cmd);
                if (message.cmd === "connect") {
                    assert.equal(message.username, "fixture-user");
                    assert.equal(message.password.toString(), "fixture-password");
                    socket.write(packet.generate({ cmd: "connack", returnCode: 0, sessionPresent: false }));
                } else if (message.cmd === "subscribe") {
                    assert.equal(message.subscriptions[0].topic, "security/probe");
                    socket.write(packet.generate({ cmd: "suback", messageId: message.messageId, granted: [0] }));
                    socket.write(packet.generate({ cmd: "publish", topic: "security/probe",
                        payload: "payload-ok", qos: 0, retain: false, dup: false }));
                } else if (message.cmd === "disconnect") {
                    socket.end();
                } else {
                    throw new Error("Unexpected MQTT packet: " + message.cmd);
                }
            } catch (error) {
                wireFailure = error;
                socket.destroy();
            }
        });
    });
    broker.listen(0, "127.0.0.1");
    await once(broker, "listening");
    try {
        const heartbeat = {};
        await new MqttMonitorType().check({ hostname: "127.0.0.1", port: broker.address().port,
            mqttUsername: "fixture-user", mqttPassword: "fixture-password", interval: 3,
            mqttTopic: "security/probe", mqttSuccessMessage: "payload-ok", mqttCheckType: "keyword" }, heartbeat);
        assert.equal(heartbeat.status, 1);
        assert.equal(heartbeat.msg, "Topic: security/probe; Message: payload-ok");
        // Kuma calls client.end() after a message. Require the real DISCONNECT too.
        const deadline = Date.now() + 2000;
        while (!seen.includes("disconnect") && Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, 10));
        }
        assert.ifError(wireFailure);
        assert.deepEqual(seen, ["connect", "subscribe", "disconnect"]);
    } finally {
        for (const socket of sockets) socket.destroy();
        await new Promise((resolve, reject) => broker.close((error) => error ? reject(error) : resolve()));
    }
}

const watchdog = setTimeout(() => { console.error("Runtime compatibility deadline exceeded"); process.exit(1); }, 15000);
(async () => {
    try {
        await sqliteAndModels();
        await mqttConsumer();
        console.log("Kuma SQLite readback, model loading and MQTT consumer passed");
    } catch (error) {
        console.error(error);
        process.exitCode = 1;
    } finally {
        clearTimeout(watchdog);
    }
})();
