/*
 * Host-side SimPoint BBV collector for KVM fast-forward.
 *
 * Uses a dedicated perf instruction-counter group (leader + IP sampler child)
 * on the KVM vCPU thread, separate from gem5's cycles/insn KVM perf group.
 */

#ifndef __CPU_KVM_BBV_COLLECTOR_HH__
#define __CPU_KVM_BBV_COLLECTOR_HH__

#include <cstdio>
#include <cstdint>
#include <memory>
#include <string>

#include "cpu/kvm/perfevent.hh"

namespace gem5
{

class BbvCollector
{
  public:
    BbvCollector();
    ~BbvCollector();

    void start(const std::string &path, uint64_t interval,
               uint64_t samplePeriod, bool excludeKernel);
    void stop();
    bool active() const { return collecting; }

    /**
     * Called after each KVM_RUN slice. Interval boundaries use instsExecuted
     * from gem5's KVM instruction counter; IP samples use the BBV perf group.
     */
    void accumulate(uint64_t instsExecuted, uint64_t totalInsnCount);

    void setInsnBaseline(uint64_t totalInsnCount);

  private:
    struct BbEntry {
        uint64_t id;
        uint64_t count;
        BbEntry *next;
    };

    struct IpEntry {
        uint64_t ip;
        uint64_t bbId;
        IpEntry *next;
    };

    static constexpr unsigned BB_MAP_BITS = 18;
    static constexpr unsigned BB_MAP_SIZE = 1u << BB_MAP_BITS;
    static constexpr unsigned IP_MAP_BITS = 18;
    static constexpr unsigned IP_MAP_SIZE = 1u << IP_MAP_BITS;

    void drainSamples();
    bool hasPendingIpSamples() const;
    void flushInterval();
    void closeCurrentBb(uint64_t ip);
    uint64_t ipToBbId(uint64_t ip);
    BbEntry *bbLookup(uint64_t id, bool create);
    void bbAdd(uint64_t id, uint64_t count);

    std::unique_ptr<PerfKvmCounter> insnLeader;
    std::unique_ptr<PerfKvmCounter> ipSampler;
    BbEntry *bbMap[BB_MAP_SIZE];
    IpEntry *ipMap[IP_MAP_SIZE];
    FILE *outfile;
    bool collecting;
    uint64_t intervalSize;
    uint64_t drift;
    uint64_t currentBb;
    uint64_t currentBbInsns;
    uint64_t nextBbId;
    uint64_t intervalsFlushed;
    uint64_t ipSamplesSeen;
};

} // namespace gem5

#endif // __CPU_KVM_BBV_COLLECTOR_HH__
