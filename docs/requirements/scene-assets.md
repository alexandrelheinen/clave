# Pinned object assets

Status: draft

## Intent

Stop cloning the full scanned-object and YCB collections to obtain the few
meshes the world spawns. Those files are fetched by URL and SHA-256, the same
way the conveyor module already is.

## Scope

**In.** The files named by `configs/world/sorting_line.yml` and the barcode
fixtures. A manifest of commit, path and digest. `scripts/import_scene_assets.py
--objects`.

**Out.** The warehouse COLLADA submodule, which is converted rather than
spawned as-is. The vendored UR10e and the Robotiq gripper. The unused ROBOTIS
menagerie, which this change stops pinning.

## Acceptance criteria

`AC-ASSET-01`: The object manifest shall name every mesh and texture path in
`configs/world/sorting_line.yml` and every barcode fixture path.

`AC-ASSET-02`: When a declared file is downloaded, the system shall write it
only after its SHA-256 matches the manifest, and shall leave a matching file
on disk untouched.

`AC-ASSET-03`: A download whose digest does not match shall raise and shall
not replace the destination.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-ASSET-01` | `test_the_manifest_covers_every_spawned_object_path` |
| `AC-ASSET-02` | `test_a_matching_file_is_not_downloaded_again` |
| `AC-ASSET-03` | `test_a_bad_download_is_refused` |

## Constraints

Credentials are not involved. The URLs are public raw files at the commits
the submodules used to pin.
