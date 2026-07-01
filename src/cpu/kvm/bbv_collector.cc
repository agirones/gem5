/*
 * Host-side SimPoint BBV collector for KVM fast-forward.
 */

#include "cpu/kvm/bbv_collector.hh"

#include <algorithm>
#include <cinttypes>
#include <cstdlib>
#include <cstring>
#include <linux/perf_event.h>
#include <vector>

#include "base/logging.hh"

namespace gem5
{

BbvCollector::BbvCollector()
    : insnLeader(std::make_unique<PerfKvmCounter>()),
      ipSampler(std::make_unique<PerfKvmCounter>()),
      bbMap{},
      ipMap{},
      outfile(nullptr),
      collecting(false),
      intervalSize(0),
      drift(0),
      currentBb(0),
      currentBbInsns(0),
      nextBbId(1),
      intervalsFlushed(0),
      ipSamplesSeen(0)
{
}

BbvCollector::~BbvCollector()
{
    if (collecting)
        stop();
}

BbvCollector::BbEntry *
BbvCollector::bbLookup(uint64_t id, bool create)
{
    const uint32_t slot = static_cast<uint32_t>(
        (id ^ (id >> 17)) & (BB_MAP_SIZE - 1));
    for (BbEntry *e = bbMap[slot]; e; e = e->next) {
        if (e->id == id)
            return e;
    }
    if (!create)
        return nullptr;

    BbEntry *e = static_cast<BbEntry *>(calloc(1, sizeof(BbEntry)));
    if (!e)
        panic("BbvCollector: calloc failed\n");

    e->id = id ? id : nextBbId++;
    e->next = bbMap[slot];
    bbMap[slot] = e;
    return e;
}

void
BbvCollector::bbAdd(uint64_t id, uint64_t count)
{
    if (!count)
        return;
    BbEntry *e = bbLookup(id, true);
    e->count += count;
}

void
BbvCollector::flushInterval()
{
    if (!outfile)
        return;

    if (currentBbInsns) {
        bbAdd(currentBb, currentBbInsns);
        currentBbInsns = 0;
    }

    size_t n = 0;
    for (unsigned i = 0; i < BB_MAP_SIZE; ++i) {
        for (BbEntry *e = bbMap[i]; e; e = e->next) {
            if (e->count)
                ++n;
        }
    }

    std::vector<BbEntry *> items;
    items.reserve(n);
    for (unsigned i = 0; i < BB_MAP_SIZE; ++i) {
        for (BbEntry *e = bbMap[i]; e; e = e->next) {
            if (!e->count)
                continue;
            items.push_back(e);
        }
    }
    std::sort(items.begin(), items.end(),
              [](const BbEntry *a, const BbEntry *b) {
                  return a->id < b->id;
              });

    fputc('T', outfile);
    for (BbEntry *e : items) {
        fprintf(outfile, ":%" PRIu64 ":%" PRIu64 " ", e->id, e->count);
        e->count = 0;
    }
    fputc('\n', outfile);
    fflush(outfile);

    ++intervalsFlushed;
    if (intervalsFlushed == 1 || (intervalsFlushed % 10) == 0) {
        inform("Host BBV: flushed %llu interval(s), %llu BBs in last line, "
               "%llu IP samples total\n",
               intervalsFlushed,
               (unsigned long long)items.size(),
               ipSamplesSeen);
    }
}

void
BbvCollector::closeCurrentBb(uint64_t ip)
{
    const uint64_t bb_id = ipToBbId(ip);
    if (!currentBb)
        currentBb = bb_id;
    bbAdd(currentBb, currentBbInsns);
    currentBbInsns = 0;
    currentBb = bb_id;
}

uint64_t
BbvCollector::ipToBbId(uint64_t ip)
{
    const uint32_t slot = static_cast<uint32_t>(
        (ip ^ (ip >> 17)) & (IP_MAP_SIZE - 1));
    for (IpEntry *e = ipMap[slot]; e; e = e->next) {
        if (e->ip == ip)
            return e->bbId;
    }

    IpEntry *e = static_cast<IpEntry *>(calloc(1, sizeof(IpEntry)));
    if (!e)
        panic("BbvCollector: calloc failed\n");

    e->ip = ip;
    e->bbId = nextBbId++;
    e->next = ipMap[slot];
    ipMap[slot] = e;
    return e->bbId;
}

void
BbvCollector::drainSamples()
{
    if (!ipSampler || !ipSampler->attached())
        return;

    ipSampler->drainIpSamples([this](uint64_t ip) {
        ++ipSamplesSeen;
        closeCurrentBb(ip);
    });
}

bool
BbvCollector::hasPendingIpSamples() const
{
    if (!ipSampler || !ipSampler->attached())
        return false;
    return ipSampler->hasPendingSamples();
}

void
BbvCollector::start(const std::string &path, uint64_t interval,
                    uint64_t samplePeriod, bool excludeKernel)
{
    if (collecting)
        stop();

    outfile = fopen(path.c_str(), "w");
    if (!outfile)
        panic("BbvCollector: failed to open %s\n", path);

    intervalSize = interval;
    drift = 0;
    currentBb = 0;
    currentBbInsns = 0;
    nextBbId = 1;
    intervalsFlushed = 0;
    ipSamplesSeen = 0;
    for (unsigned i = 0; i < BB_MAP_SIZE; ++i)
        bbMap[i] = nullptr;
    for (unsigned i = 0; i < IP_MAP_SIZE; ++i)
        ipMap[i] = nullptr;

    PerfKvmCounterConfig cfgInsn(PERF_TYPE_HARDWARE,
                                 PERF_COUNT_HW_INSTRUCTIONS);
    cfgInsn.exclude_hv(true);
    if (excludeKernel)
        cfgInsn.exclude_kernel(true);
    cfgInsn.disabled(true);

    if (insnLeader->attached())
        insnLeader->detach();
    insnLeader->attach(cfgInsn, 0);

    PerfKvmCounterConfig cfgSample(PERF_TYPE_HARDWARE,
                                   PERF_COUNT_HW_INSTRUCTIONS);
    cfgSample.exclude_hv(true);
    if (excludeKernel)
        cfgSample.exclude_kernel(true);
    cfgSample.disabled(true)
        .ipSampling(samplePeriod)
        .ringDataPages(8);

    if (ipSampler->attached())
        ipSampler->detach();
    ipSampler->attach(cfgSample, 0, *insnLeader);
    insnLeader->start();

    collecting = true;
}

void
BbvCollector::stop()
{
    if (!collecting)
        return;

    if (ipSampler && ipSampler->attached()) {
        drainSamples();
        if (drift > 0 || currentBbInsns)
            flushInterval();
        ipSampler->detach();
    }
    if (insnLeader && insnLeader->attached())
        insnLeader->detach();

    if (outfile) {
        fclose(outfile);
        outfile = nullptr;
    }

    collecting = false;
}

void
BbvCollector::setInsnBaseline(uint64_t totalInsnCount)
{
    drift = 0;
}

void
BbvCollector::accumulate(uint64_t instsExecuted, uint64_t totalInsnCount)
{
    if (!collecting)
        return;

    if (hasPendingIpSamples())
        drainSamples();

    // Interval boundaries use gem5's KVM instruction counter; attribute the
    // same user-only insns to the current basic block between IP samples.
    currentBbInsns += instsExecuted;
    drift += instsExecuted;
    while (drift >= intervalSize) {
        drainSamples();
        flushInterval();
        drift -= intervalSize;
    }
}

} // namespace gem5
