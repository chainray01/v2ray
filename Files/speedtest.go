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
    // 从环境变量获取输入输出文件路径
    inputFile := os.Getenv("INPUT_FILE")
    if inputFile == "" {
        inputFile = "../data/All_Configs_base64_Sub.txt" // 默认值
    }
    
    outputFile := os.Getenv("OUTPUT_FILE")
    if outputFile == "" {
        outputFile = "../data/test_result.txt" // 默认值
    }

    // 读取订阅链接
    bytes, err := os.ReadFile(inputFile)
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
    f, err := os.Create(outputFile)
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