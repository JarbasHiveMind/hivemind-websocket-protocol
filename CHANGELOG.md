# Changelog

## [1.0.0a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/1.0.0a1) (2026-09-03)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.11a1...1.0.0a1)

**Breaking changes:**

- feat!: v3-Noise-only — drop crypto\_key/handshake\_enabled/require\_crypto legacy handling \(companion to hivemind-core \#309\) [\#79](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/79) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.11a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.11a1) (2026-09-02)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.10a2...0.2.11a1)

**Merged pull requests:**

- fix: guard b64-audio log sniff so a typeless BUS frame cannot crash the transport [\#77](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/77) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.10a2](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.10a2) (2026-09-01)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.10a1...0.2.10a2)

**Merged pull requests:**

- test: accept close code+reason in disconnect stubs [\#75](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/75) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.10a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.10a1) (2026-09-01)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.9a1...0.2.10a1)

**Merged pull requests:**

- fix: let the disconnect callback carry a websocket close code [\#73](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/73) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.9a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.9a1) (2026-08-15)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.8a4...0.2.9a1)

**Merged pull requests:**

- fix: guard inbound decode and stop logging raw credentials [\#63](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/63) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.8a4](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.8a4) (2026-08-15)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.8a3...0.2.8a4)

**Merged pull requests:**

- docs: add AGENTS.md with per-repo agent conventions [\#66](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/66) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.8a3](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.8a3) (2026-08-15)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.8a2...0.2.8a3)

**Merged pull requests:**

- perf: stop paying for discarded logs on connection hot paths [\#68](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/68) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.8a2](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.8a2) (2026-08-15)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.8a1...0.2.8a2)

**Merged pull requests:**

- perf: validate each password once per policy [\#67](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/67) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.8a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.8a1) (2026-08-14)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.7a1...0.2.8a1)

**Merged pull requests:**

- fix: floor hivescope\>=0.7.1a1 so e2e resolves the shim with .password [\#64](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/64) ([JarbasAl](https://github.com/JarbasAl))
- fix\(tests\): accept the exception a refused key actually raises [\#62](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/62) ([goldyfruit](https://github.com/goldyfruit))

## [0.2.7a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.7a1) (2026-08-10)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.6a4...0.2.7a1)

**Merged pull requests:**

- fix: tell a refused client why its key was rejected [\#58](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/58) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.6a4](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.6a4) (2026-08-10)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.6a3...0.2.6a4)

**Merged pull requests:**

- docs: correct claims that no longer match the code [\#56](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/56) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.6a3](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.6a3) (2026-08-10)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.6a2...0.2.6a3)

**Merged pull requests:**

- chore\(ci\): drop the broken, redundant Dependabot config [\#54](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/54) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.6a2](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.6a2) (2026-08-10)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.6a1...0.2.6a2)

**Merged pull requests:**

- refactor: own the db sync debounce state in ClientDatabaseSync [\#37](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/37) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.6a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.6a1) (2026-08-10)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.5a3...0.2.6a1)

**Merged pull requests:**

- fix: disconnect ping-timeout warning false-positives on ~33% of clean disconnects [\#48](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/48) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.5a3](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.5a3) (2026-08-10)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.5a1...0.2.5a3)

**Merged pull requests:**

- test: pin that health access reads the socket peer, not a header [\#50](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/50) ([JarbasAl](https://github.com/JarbasAl))
- Add quiet local listener health endpoint [\#49](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/49) ([goldyfruit](https://github.com/goldyfruit))

## [0.2.5a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.5a1) (2026-08-03)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.4a1...0.2.5a1)

**Merged pull requests:**

- fix: say why a client disconnected [\#45](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/45) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.4a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.4a1) (2026-08-03)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.3a1...0.2.4a1)

**Merged pull requests:**

- fix: stop logging message payloads at INFO [\#42](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/42) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.3a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.3a1) (2026-08-03)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.2a2...0.2.3a1)

**Merged pull requests:**

- fix: keep websocket writes on the IOLoop [\#41](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/41) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.2a2](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.2a2) (2026-07-30)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.2a1...0.2.2a2)

**Merged pull requests:**

- docs: rewrite README in Simplified Technical English [\#39](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/39) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.2a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.2a1) (2026-07-04)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.1a1...0.2.2a1)

**Merged pull requests:**

- fix: pin poorman-handshake\>=2.0.0a1 + disable-able runtime password backstop [\#31](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/31) ([JarbasAl](https://github.com/JarbasAl))
- Add websocket ping settings [\#30](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/30) ([goldyfruit](https://github.com/goldyfruit))

## [0.2.1a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.1a1) (2026-06-06)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.0a3...0.2.1a1)

**Merged pull requests:**

- fix: drop removed message\_blacklist read \(+ sha256 cert\) [\#28](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/28) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.0a3](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.0a3) (2026-06-05)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.0a2...0.2.0a3)

**Merged pull requests:**

- docs: zero-to-hero README and /docs coverage [\#25](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/25) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.0a2](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.0a2) (2026-05-18)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.2.0a1...0.2.0a2)

**Merged pull requests:**

- docs: add /docs/ and refresh README [\#18](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/18) ([JarbasAl](https://github.com/JarbasAl))

## [0.2.0a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.2.0a1) (2026-05-18)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.1.0a1...0.2.0a1)

**Merged pull requests:**

- feat: trusted client IP from known proxies \(supersedes \#14\) [\#15](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/15) ([JarbasAl](https://github.com/JarbasAl))

## [0.1.0a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.1.0a1) (2026-05-18)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.0.4a3...0.1.0a1)

**Merged pull requests:**

- feat\(tests\): hivescope e2e suite \(supersedes \#11\) [\#21](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/21) ([JarbasAl](https://github.com/JarbasAl))

## [0.0.4a3](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.0.4a3) (2026-05-18)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.0.4a2...0.0.4a3)

**Merged pull requests:**

- ci: add standard OpenVoiceOS GitHub Actions workflows [\#19](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/19) ([JarbasAl](https://github.com/JarbasAl))

## [0.0.4a2](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.0.4a2) (2026-05-18)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.0.4a1...0.0.4a2)

**Merged pull requests:**

- Handle bad websocket auth [\#12](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/12) ([goldyfruit](https://github.com/goldyfruit))

## [0.0.4a1](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/tree/0.0.4a1) (2025-12-18)

[Full Changelog](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/compare/0.0.3...0.0.4a1)

**Merged pull requests:**

- chore: Configure Renovate [\#5](https://github.com/JarbasHiveMind/hivemind-websocket-protocol/pull/5) ([renovate[bot]](https://github.com/apps/renovate))



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
