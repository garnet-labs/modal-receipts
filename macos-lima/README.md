# Jibril on macOS through Lima

[Shirudo's macOS quickstart](https://docs.shirudo.dev/start/quickstart-macos.html) runs Shirudo on **Linux in Lima**, not on the macOS kernel. Its separate target VM requires nested KVM; this experiment runs [Jibril's Linux eBPF agent](https://jibril.garnet.ai/) in the first Linux guest only. It does not test Shirudo's inner VM or native macOS monitoring.

## Run from a fresh Mac

Download [`run-jibril.sh`](run-jibril.sh) from this repository, then paste this into a native Apple Silicon Terminal from the directory with the downloaded file:

```sh
/bin/bash ./run-jibril.sh
```

- Use a native arm64 Terminal (`uname -m` must print `arm64`). The script can run the [official Homebrew installer](https://docs.brew.sh/Installation) if needed; an unprepared Mac may prompt for administrator authorization, installation of Xcode Command Line Tools, or acceptance of its license. Follow those prompts locally.
- The script installs missing Homebrew formulae, creates a new Ubuntu 24.04 VM with 2 vCPUs, 4 GiB of RAM, and a 20 GiB virtual disk, verifies the Linux x86-64 Jibril release digest, and prints the startup attach count. It checks for a 6.8 guest kernel with function tracing and BTF before launching Jibril. It needs working HTTPS access to Homebrew, Ubuntu's image server, and GitHub.
- This is a full **x86-64 Linux guest using [QEMU software emulation](https://lima-vm.io/docs/config/vmtype/qemu/)**. It does not require Rosetta, VZ, or hardware virtualization. Rosetta's Linux support translates user-space programs in an **arm64** Linux guest; it does not provide an x86-64 Linux kernel on which to check these eBPF hooks.
- The default run is local-only (no token or registration) and leaves Jibril running in the guest. Use the stop command printed by the script, or delete the VM with `/opt/homebrew/bin/limactl delete jibril-tcg` after stopping it. The script refuses to reuse a VM name; set `JIBRIL_LIMA_INSTANCE` to an unused name to keep the prior VM.
- For an explicitly authorized [dev API canary](https://github.com/jadoonf/jibril-devin-setup/blob/b974c57c3e1a2f48968eb76a758b62adca6cfe90/docs/devin-reproducible-runbook.md#dev-canary-procedure), export `GARNET_DEV_API_TOKEN` securely, then run `JIBRIL_LIMA_INSTANCE=jibril-dev /bin/bash ./run-jibril.sh --dev-canary`. This uses Jibril v2.13.0 and garnetctl v1.19.0 and registers one GitHub-kind agent against `https://dev-api.garnet.ai`, never production. The default local-only run uses v2.17.0 like the original experiment below.

### Script verification

The [full local-only transcript](run-from-scratch.txt) records a run on an Apple M4 Pro macOS VM. The script installed missing Lima, guest agents, and QEMU, downloaded Ubuntu into a fresh Lima state, checked `CONFIG_FUNCTION_TRACER=y`, and reported **72 attached programs, 37 live links**, with zero load, attach, or link errors and an active service.

Homebrew and Xcode were already present on that host. Installing Homebrew itself, Xcode Command Line Tools/license prompts, and administrator authorization on a bare physical Mac were not exercised. Neither VZ nor Rosetta is used by the script; neither is validated by this run.

The separate [dev canary transcript](dev-canary.txt) records one GitHub-kind registration after the kernel and merged-policy checks. The first readiness check used a v2.17.0-only log message and timed out even though v2.13.0 was running. Rechecking the corrected readiness and link counting on that same service found **40 live kernel eBPF links owned by Jibril**. The dev API returned events for that agent. This checks startup and events, not periodic or final profile submission.

## Original experiment (PR #14)

**Result: Jibril v2.17.0 loaded 72 of 76 program candidates: 40 with their own links (including 3 iterators) and 32 tail-call programs in program arrays.** The loader reported zero load, attach, or link errors on Ubuntu 24.04.5 (`6.8.0-147-generic`, x86-64) in a software-emulated Lima guest ([guest transcript](guest.txt)). The same Jibril release reported [0 of 76 on Modal](https://github.com/garnet-labs/modal-receipts/blob/da07caefbceaa7d116256e64ce7f558ef3714d14/kernel/README.md#L19-L30).

## Why it attached here

- The Ubuntu guest kernel has `FTRACE`, `FUNCTION_TRACER`, `KPROBES`, `DEBUG_INFO_BTF`, `BPF_EVENTS`, and `MODULES` enabled, and exports `/sys/kernel/btf/vmlinux` and tracefs events. [The Modal kernel lacked those attachment prerequisites or capabilities](https://github.com/garnet-labs/modal-receipts/blob/da07caefbceaa7d116256e64ce7f558ef3714d14/kernel/README.md#L19-L30). The [guest transcript](guest.txt) records the kernel config and shows working tracing, perf-event and raw-tracepoint BPF links. Module support is a compatibility difference; no module install or kernel replacement was needed for this run.
- Jibril's 76-program metric counts [program descriptors before kernel loading](https://github.com/garnet-org/jibril/blob/3478c051434fdff3d921c86cae9feffa21fb21a6/pkg/singleton/ebpf/engine.go#L201-L224). The loader [chooses exactly one candidate per socket hook group](https://github.com/garnet-org/jibril/blob/3478c051434fdff3d921c86cae9feffa21fb21a6/pkg/singleton/ebpf/prog.go#L188-L230). `bpftool` saw the primary target for [each of the four groups](https://github.com/garnet-org/jibril/blob/3478c051434fdff3d921c86cae9feffa21fb21a6/pkg/singleton/ebpf/prog.go#L40-L68) and none of their four fallbacks, so the difference was alternate hooks left unused, not attachment failures ([BTF target comparison](guest.txt)).
- The startup log reported 37 live links. After startup, the before/after `bpftool` ID comparison found 72 new programs: 40 with links (including three iterator links) and 32 [`tail_` programs that populate program arrays without their own links](https://github.com/garnet-org/jibril/blob/3478c051434fdff3d921c86cae9feffa21fb21a6/pkg/singleton/ebpf/bond-tail.go#L74-L99). The offline service was active at capture ([guest transcript](guest.txt)).

## Host and VM

On this virtual Apple M4 Pro Mac, `kern.hv_support` was `0`. Even the stock Ubuntu guest (no nested VM) failed at VZ startup: `VZErrorDomain Code=2`, “Virtualization is not available on this hardware.” The [host transcript](host.txt) has the exact error. This is a limit of this Mac VM, not a result for physical Apple Silicon Macs.

```sh
brew install lima
limactl start --tty=false --name=jibril-stock template:ubuntu-24.04
```

**Custom fallback:** use [Lima's QEMU driver](https://lima-vm.io/docs/config/vmtype/qemu/) with an x86-64 guest, instead of the [quickstart's arm64 Ubuntu 26.04 VZ template](https://github.com/shirudo-dev/shirudo/blob/main/infra/lima/shirudo.yaml). The public [v2.13.0](https://github.com/garnet-org/jibril-releases/releases/tag/v2.13.0) and [v2.17.0](https://github.com/garnet-org/jibril-releases/releases/tag/v2.17.0) binaries checked here were Linux x86-64 ELF files. QEMU used software emulation (`-accel tcg`), as recorded in the [host transcript](host.txt).

```sh
brew install qemu
brew install lima-additional-guestagents
limactl start --tty=false --name=jibril-tcg --vm-type=qemu --arch=x86_64 \
  --cpus=2 --memory=4 --disk=20 --mount-none --containerd=none \
  --timeout=15m template:ubuntu-24.04
```

## Jibril install and local-only run

This uses the documented [standalone binary install](https://jibril.garnet.ai/install/standalone.html), pinned to [v2.17.0](https://github.com/garnet-org/jibril-releases/releases/tag/v2.17.0) so it matches the [Modal comparison](https://github.com/garnet-labs/modal-receipts/blob/da07caefbceaa7d116256e64ce7f558ef3714d14/kernel/README.md#L19-L30). The digest matched the [release checksum](https://github.com/garnet-org/jibril-releases/releases/download/v2.17.0/SHA256SUMS). Copy the verified Linux binary to the guest rather than trying to execute it on macOS.

```sh
curl -fL -o "$HOME/jibril-v2.17.0" \
  https://github.com/garnet-org/jibril-releases/releases/download/v2.17.0/jibril
shasum -a 256 "$HOME/jibril-v2.17.0"
guest_home=$(limactl shell jibril-tcg -- printenv HOME)
limactl copy --backend=scp "$HOME/jibril-v2.17.0" "jibril-tcg:$guest_home/jibril-v2.17.0"
limactl shell jibril-tcg
```

In the guest:

```sh
sudo install -m 0755 "$HOME/jibril-v2.17.0" /usr/local/bin/jibril
sudo /usr/local/bin/jibril --version
```

`bpftool` was already present on the selected Ubuntu image. The optional `sudo apt-get update && sudo apt-get install -y --no-install-recommends linux-tools-common linux-tools-$(uname -r)` upgraded two ancillary packages, not the boot kernel ([guest transcript](guest.txt)).

**Custom local-only launch:** the first run, with an empty environment and no token, finished loading the eBPF programs and then exited because agent initialization required a project token ([guest transcript](guest.txt)). The second run uses the release's [`GARNET_SAR` registration bypass](https://github.com/garnet-org/jibril/blob/3478c051434fdff3d921c86cae9feffa21fb21a6/pkg/services/agent/engine.go#L33-L54) and [`GARNET_SAR_PRINTER` printer bypass](https://github.com/garnet-org/jibril/blob/3478c051434fdff3d921c86cae9feffa21fb21a6/pkg/printers/garnet/garnet.go#L35-L56). No credentials are passed and no Garnet agent is registered or profiles submitted.

```sh
sudo systemd-run --unit=jibril-local-offline --property=Type=exec \
  /usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  GARNET_SAR=true GARNET_SAR_PRINTER=true /usr/local/bin/jibril

# systemd-run returns before Jibril reaches its exec phase.
invocation_id=$(systemctl show -p InvocationID --value jibril-local-offline)
sudo timeout 180 sh -c '
  until journalctl "_SYSTEMD_INVOCATION_ID=$1" --no-pager -o cat | grep -Fq "$2"; do
    sleep 1
  done
' sh "$invocation_id" "hierarchy phase 'exec' scheduled 'pkg'" ||
  echo 'Jibril did not reach exec within 180s; check the journal below.' >&2

sudo journalctl -u jibril-local-offline --no-pager -o cat
sudo bpftool prog show
sudo bpftool link show
```

For the kernel-side comparison, save `sudo bpftool -j prog show` and `sudo bpftool -j link show` before starting the service and again after Jibril reaches `exec`, then compare ID sets rather than subtracting the total row counts ([guest transcript](guest.txt)).
