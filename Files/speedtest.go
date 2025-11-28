package main

import (
    "context"
    "fmt"
    "os"
    "sort"
    "strings"
    "time"

    "github.com/xxf098/lite-proxy/web"
    "github.com/xxf098/lite-proxy/profile/download"
)

// 统一结果结构体
type SpeedResult struct {
    ID       int
    Remarks  string
    Ping     int
    AvgSpeed int64
    MaxSpeed int64
    Link     string
    IsOk     bool
}

func main() {
    ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
    defer cancel()

    // 1. 读取订阅
    sub, err := loadSubscription("../data/All_Configs_base64_Sub.txt")
    if err != nil {
        panic(err)
    }

    // 2. 配置测速参数
    opts := web.ProfileTestOptions{
        Subscription:  sub,
        GroupName:     "Default",
        SpeedTestMode: "pingonly",
        PingMethod:    "googleping",
        SortMethod:    "rspeed",
        Concurrency:   32,
        TestMode:      2,
        Language:      "en",
        Timeout:       1 * time.Second,
    }

    // 3. 执行异步测速
    results, err := runAsyncSpeedTest(ctx, opts)
    if err != nil {
        panic(err)
    }

    // 4. 排序（按 avg/max/ping）
    sortResults(results)

    // 5. 写结果到文件
    saveResults("../data/test_result.txt", results)

    fmt.Printf("测速完成，共 %d 个有效节点\n", len(results))
}

/////////////////////////////////////////////////
//                核心逻辑
/////////////////////////////////////////////////

func runAsyncSpeedTest(ctx context.Context, opts web.ProfileTestOptions) ([]SpeedResult, error) {

    nodeChan, links, err := web.TestAsyncContext(ctx, opts)
    if err != nil {
        return nil, err
    }

    count := len(links)
    results := make([]SpeedResult, 0, count)

    for i := 0; i < count; i++ {
        node := <-nodeChan
        if node.IsOk {
            results = append(results, SpeedResult{
                ID:       node.Id,
                Remarks:  node.Remarks,
                Ping:     node.Ping,
                AvgSpeed: node.AvgSpeed,
                MaxSpeed: node.MaxSpeed,
                Link:     links[node.Id],
                IsOk:     true,
            })
        }
    }

    return results, nil
}

/////////////////////////////////////////////////
//                辅助函数
/////////////////////////////////////////////////

func loadSubscription(file string) (string, error) {
    bytes, err := os.ReadFile(file)
    if err != nil {
        return "", fmt.Errorf("cannot read sub file: %v", err)
    }

    link := strings.TrimSpace(string(bytes))
    if link == "" {
        return "", fmt.Errorf("subscription empty")
    }
    return link, nil
}

func sortResults(r []SpeedResult) {
    sort.Slice(r, func(i, j int) bool {
        // 优先按 Ping 排
        if r[i].Ping != r[j].Ping {
            return r[i].Ping < r[j].Ping
        }
        // 再按 AvgSpeed
        if r[i].AvgSpeed != r[j].AvgSpeed {
            return r[i].AvgSpeed > r[j].AvgSpeed
        }
        // 最后按 MaxSpeed
        return r[i].MaxSpeed > r[j].MaxSpeed
    })
}

func saveResults(path string, results []SpeedResult) {
    f, err := os.Create(path)
    if err != nil {
        panic(err)
    }
    defer f.Close()

    for _, r := range results {
        _, _ = f.WriteString(
            fmt.Sprintf("%s | ping: %d | avg: %s | max: %s | %s\n",
                r.Remarks,
                r.Ping,
                download.ByteCountIECTrim(r.AvgSpeed),
                download.ByteCountIECTrim(r.MaxSpeed),
                r.Link,
            ),
        )
    }
}
