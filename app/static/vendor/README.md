# Vendored front-end assets

Everything the UI loads lives in this folder. Nothing is fetched from a CDN at runtime.

| File | Package | Version | Licence | Source |
|---|---|---|---|---|
| `chart.umd.js` | chart.js | 4.4.7 | MIT (`Chart.js-LICENSE.md`) | npm registry tarball `chart.js-4.4.7.tgz`, file `package/dist/chart.umd.js`, copied unmodified |

## Verify

```
shasum -a 256 app/static/vendor/chart.umd.js
# 2812cb8825fdc57469eb2f7bb055e9429244e599920511ee477e828499b632cb
```

To reproduce: download `chart.js-4.4.7.tgz` from the npm registry (its SHA-1 is
`7a01ee0b4dac3c03f2ab0589af888db296d896fa`, matching `npm view chart.js@4.4.7 dist.shasum`),
extract it, and hash `package/dist/chart.umd.js`.
