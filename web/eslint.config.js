const { FlatCompat } = require("@eslint/eslintrc");

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

module.exports = [
  {
    ignores: [".next/**", "node_modules/**", "out/**", "dist/**", "build/**"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

