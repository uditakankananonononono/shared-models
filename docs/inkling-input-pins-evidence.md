# Inkling serving inputs: revision pins and dirty-tree check (SM-PEER-2)
Status: authored, not run. Metadata only: no weights, GGUFs or other model files were downloaded.
Base: shared-models a215196a3eca7dd4e571f853a9d5c91ee9984f05 (resolves; read-only public clone).
READ = observed in the cited response/source. ASSUMED = my inference, labelled.

## 1. Repo commit SHAs (HF public model API)
| Repo | URL queried | Observed UTC | Value (`sha`) | lastModified |
|---|---|---|---|---|
| thinkingmachines/Inkling-Small-NVFP4 | https://huggingface.co/api/models/thinkingmachines/Inkling-Small-NVFP4?blobs=true | 2026-10-10T06:58:08Z | `b6a99534467840620d411e4cd4ad5819b2610d9c` | 2026-07-30T17:56:54.000Z |
| unsloth/Inkling-Small-GGUF | https://huggingface.co/api/models/unsloth/Inkling-Small-GGUF?blobs=true | 2026-10-10T06:58:08Z | `1a19ef82883cb7b9c581b93c30ea252dabbf658d` | 2026-07-31T03:56:12.000Z |

Both: gated=false, private=false, disabled=false (READ). The same `sha` is returned by the plain URL without `?blobs=true`
(READ, 2026-10-10T06:58:03Z) and equals `branches[main].targetCommit` of `.../api/models/<repo>/refs` (READ, 2026-10-10T06:58:56Z).
Spec deviation, flagged: the spec says "https://huggingface.co/api/models/<repo>" only. File sizes and LFS oids are returned
only with the `?blobs=true` query on that same endpoint (the plain response lists file names only: READ). No other host was used.
Re-query: `curl -s https://huggingface.co/api/models/<repo>?blobs=true | jq '.sha, (.siblings[]|[.rfilename,.size,.lfs.sha256])'`.
The commit moves whenever the repo is pushed; a mismatch later means the repo changed, not that this table was wrong.

## 2. GGUF files for the script's QUANT (LFS sha256 oid, metadata size in bytes; from the unsloth response above)
Script default `INKLING_QUANT=UD-Q2_K_XL`; the script comment also names UD-Q3_K_XL and UD-Q4_K_XL, so all three are listed.

| File (in repo) | Size (bytes) | LFS sha256 |
|---|---|---|
| UD-Q2_K_XL/Inkling-Small-UD-Q2_K_XL-00001-of-00003.gguf | 12986592 | `66bfa27a88b457cebff967b449599fc412f094dc84d682fb90a5d6586d2897ff` |
| UD-Q2_K_XL/Inkling-Small-UD-Q2_K_XL-00002-of-00003.gguf | 49908961312 | `6a81a926cb7383e3dd2ca4d83ff90228403425875137ac2264df8cfab9bd8b8a` |
| UD-Q2_K_XL/Inkling-Small-UD-Q2_K_XL-00003-of-00003.gguf | 38017887968 | `5692c6150bd58d2c05ab49cd7e975edbb026866045cb912788110135469f4c12` |
| UD-Q3_K_XL/Inkling-Small-UD-Q3_K_XL-00001-of-00004.gguf | 12986592 | `110190a3c20fbc6d9783125184e470ab7479a79bee7bdf4b5ceda2a6a736f496` |
| UD-Q3_K_XL/Inkling-Small-UD-Q3_K_XL-00002-of-00004.gguf | 49513784096 | `8df5f2d79e206f7edfc811303c352734c95dc05a2e6c7bc0192c967fdd783d7f` |
| UD-Q3_K_XL/Inkling-Small-UD-Q3_K_XL-00003-of-00004.gguf | 49969966752 | `6078bcbe08ad005feb3cfd87dd2a21258101197bcefee9d7d6c65eb94317f4bb` |
| UD-Q3_K_XL/Inkling-Small-UD-Q3_K_XL-00004-of-00004.gguf | 20057642400 | `dd0f2e32d7ca2fabb7b1c40e8bcbc1f951e8271c42b31f8c318c002b7cdc4209` |
| UD-Q4_K_XL/Inkling-Small-UD-Q4_K_XL-00001-of-00005.gguf | 12986592 | `a51ac3f439198f2817219edd582be4b600c273be24e78cbd58ebff982d9f007e` |
| UD-Q4_K_XL/Inkling-Small-UD-Q4_K_XL-00002-of-00005.gguf | 49010259680 | `ce586d0d77c0f31d4a137ae3682f1b2748149dbe15344db7a72328ef758835cc` |
| UD-Q4_K_XL/Inkling-Small-UD-Q4_K_XL-00003-of-00005.gguf | 49237390240 | `1a7edf29bda1d278b4668e1a082d7db634b845a53ea58c918a8cea1f9006c21c` |
| UD-Q4_K_XL/Inkling-Small-UD-Q4_K_XL-00004-of-00005.gguf | 49458817088 | `376f67568438da96b10566730e8a9e17e3f665ab1b9d82eba48ec33708b172f7` |
| UD-Q4_K_XL/Inkling-Small-UD-Q4_K_XL-00005-of-00005.gguf | 15554440512 | `71fff4727f0fbecba426cd75e62b4194779cf1488666b5d4bc040ca4227b4b04` |

- UD-Q2_K_XL total: 87939835872 bytes (87.9 GB)
- UD-Q3_K_XL total: 119554379840 bytes (119.6 GB)
- UD-Q4_K_XL total: 163273894112 bytes (163.3 GB)

mmproj files that `-hf` also fetches by default (see section 3, arg.cpp:3075):

| File | Size (bytes) | LFS sha256 |
|---|---|---|
| mmproj-BF16.gguf | 138684128 | `05d4475a956030be87b099865d6552a541a476db8cc3e266fcfa7c5a24846248` |
| mmproj-F16.gguf | 138684128 | `bf1e6afc9889151b3fee61119d3ee2cd224b59a1d881cdf87e33962f64aecc7e` |
| mmproj-F32.gguf | 277311968 | `653c88aab6699d65ecd45d82303a74a467309dcb8e837e0c9e18f394f4ee3def` |

Which mmproj file llama.cpp would pick is decided by `find_best_mmproj` (download.cpp:597-599); I did not trace its choice (ASSUMED not needed for text serving).

## 2b. thinkingmachines/Inkling-Small-NVFP4 files (same API, `?blobs=true`; total listed size 170764923366 bytes)
| File | Size (bytes) | LFS sha256 (large files only) | git blobId |
|---|---|---|---|
| .gitattributes | 1570 | - | `52373fe24473b1aa44333d318f578ae6bf04b49b` |
| README.md | 44004 | - | `7f2b6b89fb526643c2c4f6dcd9f98c70c2b7a170` |
| chat_template.jinja | 6294 | - | `04c53c7d1f9832f8cce2dab9cbde247a1c66b680` |
| config.json | 2214 | - | `b4889a3be4cd8670a930b01e1cba45f7e706438d` |
| hf_quant_config.json | 14102 | - | `619544e348d447a09099e35aca3e30bcab5872b4` |
| model-00001-of-00009.safetensors | 19797851172 | `0536fc0774c061f006fbc0f8062300b80f7fa3c6395753f9558a53231ccdfdaf` | `eefd50470d8fb64f7694ab3675d104724f02c44d` |
| model-00002-of-00009.safetensors | 18832947622 | `94046cd4c60e9f8b84e646af29b48d972b16328ef16c68e1d224e7cc1c108f69` | `3f69f622636dedb21f7e2f587e303baeb7b0fa20` |
| model-00003-of-00009.safetensors | 19460482192 | `5b011d77adab48cfedab8d82da3ee45e9658a298b5a2efe79386c9f80be83c90` | `ffc4215435e2cbb25e70073e954dd7c417cbfdab` |
| model-00004-of-00009.safetensors | 19886208500 | `f84efa4eab97da5d95e42813cd40a682439cfbd6cbdc9e644cc2aed650034b66` | `2f2d5008326e6dca55469486f69e5ceb6c59d1b3` |
| model-00005-of-00009.safetensors | 19970085622 | `04911920af137efb2bac5a8a3c65b1cd727b1c8f0a6ddcc691534c52e5cb3dce` | `ca2dd0d388ef8f35aa51008b531e69e5876994d1` |
| model-00006-of-00009.safetensors | 18910731870 | `6f2e9eb03063a3cdbc9361fd7f203d213476d7ca3295fe45757e2fe1f26513a8` | `89e1722a351728dbcb4c35d7fa033672d5103325` |
| model-00007-of-00009.safetensors | 15485561834 | `728792823d6ba5b214503a3d75d39bbd239ba129a40b34ddb67f6d93e03fc0df` | `18e9936a07441b119d16128340242a38aa6b75dd` |
| model-00008-of-00009.safetensors | 19791451186 | `dc821c24f1af8342e02a456f06315c8c6c1e374d2060e258864117a660fbf37e` | `e70759dd12d372fbba1f32ce67f782edb92f1434` |
| model-00009-of-00009.safetensors | 14134068242 | `c91d957b4a0cf277822f4174a5bc6071eec51b0c7243f53069c6f3e3bb8a93fb` | `7db8d96c2f4840030ccd102cc339dab7ea4c9f9e` |
| model.safetensors.index.json | 116141 | - | `72a2576abd9e6956d79a43a985f85424843f8270` |
| mtp.safetensors | 4463845392 | `d286dd21cb982a0052d24ee0077ec6fc38f5a766dc6953e6c4b85c6473bfa7b3` | `391aa575175af901663ab01922429eed221fb30a` |
| processor_config.json | 1110 | - | `5119c4247a30de9fea35fe269cc786db37b8d67b` |
| special_tokens_map.json | 517 | - | `0c6ed62743194dc98ba50d3ca338bf906503b80b` |
| tiktoken/tokenizer.model | 3615874 | `bc253fd2b702f7a6da7105eaa8f3463b2f1247e83614f23e5323b921088bed2a` | `9367ddda1a28202d89d24db9b93f34e1834ea01c` |
| tokenizer.json | 27875797 | `9fb6333a7db8fe5da90728e741e4a3ee4ac2ae12c5dd4958cc6f31688787d3c2` | `8375e6ba74d80af765dbaf2acbaffd33885ad379` |
| tokenizer_config.json | 12111 | - | `3f7b53bb76be489908376923167e78d060fa20c6` |

## 3. Pinning mechanisms (cited; line numbers are of the raw file at the named revision)
### vLLM v0.31.0 (https://raw.githubusercontent.com/vllm-project/vllm/v0.31.0/<path>)
- `--revision`, `--code-revision`, `--tokenizer-revision` flags: vllm/engine/arg_utils.py:946-949.
- Meaning (branch, tag or commit id; default "default version"): vllm/config/model.py:206-216.
- Tokenizer revision defaults to the model revision: vllm/config/model.py:564-565.
- Revision resolved once to a commit: vllm/config/model.py:592-596; `resolve_revision` is best effort and returns the revision unchanged if it cannot resolve: vllm/transformers_utils/repo_utils.py:52-74 (a 40-hex commit is already a commit; ASSUMED unchanged).
- `trust_remote_code` code revision is passed separately, `code_revision` (None unless set): vllm/config/model.py:635-639. Because the script uses `--trust-remote-code`, `--code-revision` must be pinned too, or code comes from the repo's default branch (READ: "If unspecified, will use the default version", model.py:209-212).
### llama.cpp 68cd3f6cb06b1e425ea7221af03a93099aa6ab84 (https://raw.githubusercontent.com/ggml-org/llama.cpp/68cd3f6cb06b1e425ea7221af03a93099aa6ab84/<path>)
- `-hf/--hf-repo` help: "<user>/<model>[:quant]"; mmproj also downloaded unless `--no-mmproj`: common/arg.cpp:3073-3081. `-hff/--hf-file` overrides the quant: arg.cpp:3083-3088.
- The text after ':' is only a quant tag: common/download.cpp:67-75 (`tag = parts.back()`), used in `find_best_model(all, tag)` at download.cpp:732.
- **`-hf` has no revision syntax (READ: no revision field in `common_download_split_repo_tag`, download.cpp:67-75, or in the `-hf` option, arg.cpp:3073-3081).** It resolves the repo's `main` branch: refs API `api/models/<repo>/refs` at common/hf-cache.cpp:210, branch name "main" selected at hf-cache.cpp:243, commit used at :280, tree listing at :293, file URLs `.../resolve/<commit>/...` at :331.
- Offline cache pick: `get_cached_ref` prefers refs file named "main", else any other: hf-cache.cpp:360-377; `--offline` flag: arg.cpp:3952-3955; offline use at download.cpp:699-704.
- Alternatives (proposed in the patch, nothing downloaded here): (a) INKLING_GGUF_DIR with local shards verified by sha256 against section 2 and `-m <first shard>`; (b) preflight that refuses to start unless `main` equals the pinned commit, then `-hf`. (b) leaves a race between the check and llama-server's own refs lookup. `-m` with first shard of a split GGUF is ASSUMED to load the remaining shards (not read in this unit).

## 4. Dirty-tree / stale-build check (proposed)
- Existing script treats `HEAD==PIN_SHA` as clean (READ in base serve_llamacpp.sh); the proposed patch adds `git status --porcelain -- . ':(exclude)build'` and dies on any output (no auto-clean).
- Stale build: stamp file `build/.inkling-build-stamp` = `"<PIN_SHA> GGML_CUDA=<value>"`; build reused only when the stamp matches, otherwise `rm -rf build` and rebuild. ASSUMED: build/ holds only build products (untracked `build` is excluded from the dirty check by pathspec).
- Existing `PIN_SHA` and `INKLING_VLLM_IMAGE` lines are unchanged in the patch (READ in diff).

## 5. UNPROVEN
- End-to-end serving, Inkling compatibility of v0.31.0 or of llama.cpp 68cd3f6 with these exact weights; that vLLM accepts `--code-revision` together with Inkling's tokenizer mode; that llama-server loads `-m <first shard>`; the proposed scripts have never been executed (syntax-only `bash -n`).
- The PR 25731 head is mutable; the HF repos can be force-pushed; the registry/Hub values were read once.
- Spec URL for the repo: `https://github.com/uditakankananononono/shared-models` does not resolve (git asked for credentials); `https://github.com/uditakankananonononono/shared-models` (one more "no") resolves and its HEAD is the stated base. I used the latter.
