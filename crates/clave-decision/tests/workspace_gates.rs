//! The workspace configuration the first crate brought with it.
//! of the build configuration rather than of a running function, so the test
//! reads the committed files and fails when a gate is removed from them.
#![expect(clippy::unwrap_used, reason = "test assertions")]

const WORKSPACE_MANIFEST: &str = include_str!("../../../Cargo.toml");
const VALIDATE_SCRIPT: &str = include_str!("../../../scripts/validate.sh");
const CI_WORKFLOW: &str = include_str!("../../../.github/workflows/ci.yml");
const TOOLCHAIN: &str = include_str!("../../../rust-toolchain.toml");

/// The validation script runs formatting, lint, test,
/// documentation, dependency, and coverage checks, and stops at the first
/// failure.
#[test]
fn the_validation_script_runs_every_gate_and_stops_at_the_first_failure() {
    for step in [
        "cargo fmt --all --check",
        "cargo clippy --all-targets --all-features -- -D warnings",
        "cargo nextest run --all-features",
        "cargo test --doc",
        "cargo doc --no-deps --all-features",
        "cargo deny check",
        "cargo llvm-cov --all-features --fail-under-lines 80",
    ] {
        assert!(
            VALIDATE_SCRIPT.contains(step),
            "the validation script does not run {step}"
        );
    }
    assert!(VALIDATE_SCRIPT.contains("set -euo pipefail"));
}

/// Continuous integration runs that same script rather than a
/// second copy of the steps, so a local result and a remote result cannot
/// disagree.
#[test]
fn continuous_integration_runs_the_same_script_a_contributor_runs() {
    assert!(CI_WORKFLOW.contains("./scripts/validate.sh"));
    assert!(!CI_WORKFLOW.contains("cargo clippy"));
    assert!(!CI_WORKFLOW.contains("cargo nextest run"));
}

/// The coverage gate fails below 80 percent of lines.
#[test]
fn the_coverage_gate_fails_below_eighty_percent_of_lines() {
    assert!(VALIDATE_SCRIPT.contains("--fail-under-lines 80"));
}

/// A release build keeps overflow checks on, so an arithmetic
/// overflow on the decision path faults instead of producing a wrapped value.
#[test]
fn a_release_build_faults_on_overflow_rather_than_wrapping() {
    let profile_at = WORKSPACE_MANIFEST.find("[profile.release]").unwrap();
    let profile = WORKSPACE_MANIFEST.get(profile_at..).unwrap();

    assert!(profile.contains("overflow-checks = true"));
}

/// The two crates on the decision path carry the hardened lint
/// tier, which is what makes an unnamed overflow a build failure rather than a
/// runtime surprise.
#[test]
fn the_decision_path_crates_carry_the_hardened_lint_tier() {
    for manifest in [
        include_str!("../Cargo.toml"),
        include_str!("../../clave-publish/Cargo.toml"),
    ] {
        for lint in [
            "arithmetic_side_effects = \"deny\"",
            "as_conversions = \"deny\"",
            "indexing_slicing = \"deny\"",
            "cast_possible_truncation = \"deny\"",
        ] {
            assert!(
                manifest.contains(lint),
                "a hardened crate is missing {lint}"
            );
        }
    }
}

/// The documentation build denies warnings, so a reference that
/// does not resolve fails the gate.
#[test]
fn an_unresolved_documentation_reference_fails_the_build() {
    assert!(VALIDATE_SCRIPT.contains("RUSTDOCFLAGS=\"-D warnings\" cargo doc"));
}

/// The toolchain is pinned with the components every gate needs,
/// so a local run and a remote run compile with the same compiler.
#[test]
fn the_toolchain_is_pinned_with_the_components_the_gates_need() {
    for component in ["rustfmt", "clippy", "llvm-tools-preview"] {
        assert!(TOOLCHAIN.contains(component));
    }
    assert!(TOOLCHAIN.contains("channel"));
}
