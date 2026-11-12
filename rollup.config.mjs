import commonjs from "@rollup/plugin-commonjs";
import json from "@rollup/plugin-json";
import nodeResolve from "@rollup/plugin-node-resolve";
import terser from "@rollup/plugin-terser";
import typescript from "rollup-plugin-typescript2";

const dev = !!process.env.ROLLUP_WATCH;

const bundle = (input, file) => ({
  input,
  output: { file, format: "es" },
  plugins: [
    nodeResolve(),
    json(),
    typescript(),
    commonjs(),
    !dev && terser({ format: { comments: false } }),
  ],
});

export default [
  bundle("js/loader/main.ts", "custom_components/iconhub/loader.js"),
  bundle("js/panel/main.ts", "custom_components/iconhub/panel.js"),
];
