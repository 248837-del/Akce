const assert = require("node:assert/strict");
const { test } = require("node:test");
const { rozdelCenuHalere } = require("./vypocet.js");

test("poměrně rozdělí cenu a zbytek haléřů přidělí stabilně", () => {
  assert.deepEqual(rozdelCenuHalere(100, [1, 1, 1]), [34, 33, 33]);
  assert.deepEqual(rozdelCenuHalere(1000, [1, 2, 0]), [333, 667, 0]);
});

test("při nulových počtech ponechá cenu nerozdělenou", () => {
  assert.deepEqual(rozdelCenuHalere(23990, [0, 0]), [0, 0]);
});

test("odmítne neplatnou cenu nebo počty", () => {
  assert.throws(() => rozdelCenuHalere(-1, [1]), TypeError);
  assert.throws(() => rozdelCenuHalere(100, [1.5]), TypeError);
});
