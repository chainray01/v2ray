package main

import (
    "context"
    "fmt"
    "os"
    "strings"
    "time"
    "github.com/xxf098/lite-proxy/web"
)

func main() {
    // 读取订阅链接
    bytes, err := os.ReadFile("../data/All_Configs_base64_Sub.txt")
    if err != nil {
        panic(fmt.Sprintf("cannot read subscription file: %v", err))
    }

    link := strings.TrimSpace(string(bytes))
    if link == "" {
        panic("subscription content is empty")
    }

    opts := web.ProfileTestOptions{
        Subscription:  link,
        GroupName:     "Default",
        SpeedTestMode: "pingonly",
        PingMethod:    "googleping",
        SortMethod:    "rspeed",
        Concurrency:   32,
        TestMode:      2,
        Language:      "en",
        FontSize:      24,
        Theme:         "rainbow",
        Unique:        true,
        Timeout:       1 * time.Second,
        OutputMode:    0,
    }

    // 打开文件写入
    f, err := os.Create("../data/test_result.txt")
    if err != nil {
        panic(fmt.Sprintf("cannot create output file: %v", err))
    }
    defer f.Close()

    // 使用异步方式测试
    nodeChan, links, err := web.TestAsyncContext(context.Background(), opts)
    if err != nil {
        panic(err)
    }

    count := len(links)
    fmt.Printf("Total nodes to test: %d\n", count)

    // 接收测试结果
    for i := 0; i < count; i++ {
        node := <-nodeChan
        if node.IsOk {
            // 写入文件
            _, _ = f.WriteString(node.Remarks + "\n")

        }
    }

    close(nodeChan)
    fmt.Println("Test completed!")
}