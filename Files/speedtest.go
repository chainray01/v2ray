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
        Concurrency:   16,
        TestMode:      2,
        Language:      "en",
        FontSize:      24,
        Theme:         "rainbow",
        Unique:        true,
        Timeout:       0.5 * time.Second,
        OutputMode:    0,
    }

    nodes, err := web.TestContext(context.Background(), opts, &web.EmptyMessageWriter{})
    if err != nil {
        panic(err)
    }

    // 打开文件写入
    f, err := os.Create("../data/test_result.txt")
    if err != nil {
        panic(fmt.Sprintf("cannot create output file: %v", err))
    }
    defer f.Close()

    for _, node := range nodes {
        if node.IsOk {
            _, _ = f.WriteString(node.Remarks + "\n")  // 写入文件
            //fmt.Println(node.Remarks)                  // 同时输出到 stdout（可选）
        }
    }
}
