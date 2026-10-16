"""Execution CPU and target ABI are independent preset constraints."""

def exec_constraints(cpu):
    return ["@platforms//os:linux", "@platforms//cpu:" + cpu]

def target_constraints(cfg):
    result = exec_constraints(cfg["target_cpu"]) + ["//bazel/toolchain:glibc_" + ("cross" if cfg["is_cross"] else "native")]
    if cfg["is_cross"]:
        result.append("//bazel/toolchain:from_" + cfg["host_cpu"])
    return result
