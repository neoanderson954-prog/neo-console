using System.Text.Json;
using NeoConsole.Services;
using Xunit;

namespace NeoConsole.Tests;

public class ClaudeProcessTests
{
    [Fact]
    public void ExtractToolOutput_String_ReturnsString()
    {
        var json = JsonDocument.Parse("\"hello world\"").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Equal("hello world", result);
    }

    [Fact]
    public void ExtractToolOutput_EmptyString_ReturnsEmpty()
    {
        var json = JsonDocument.Parse("\"\"").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Equal("", result);
    }

    [Fact]
    public void ExtractToolOutput_Object_WithFileContent_ReturnsContent()
    {
        var json = JsonDocument.Parse("""
            {
                "type": "text",
                "file": {
                    "content": "file content here"
                }
            }
            """).RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Equal("file content here", result);
    }

    [Fact]
    public void ExtractToolOutput_Object_WithoutFileContent_ReturnsJson()
    {
        var json = JsonDocument.Parse("""{"some": "object"}""").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Contains("some", result);
        Assert.Contains("object", result);
    }

    [Fact]
    public void ExtractToolOutput_Array_ReturnsJsonString()
    {
        var json = JsonDocument.Parse("[1, 2, 3]").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Contains("1", result);
    }

    [Fact]
    public void ExtractToolOutput_Number_ReturnsString()
    {
        var json = JsonDocument.Parse("42").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Equal("42", result);
    }

    [Fact]
    public void ExtractToolOutput_Null_ReturnsEmpty()
    {
        // Null falls through to default case which returns ToString() = ""
        var json = JsonDocument.Parse("null").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Equal("", result);
    }

    [Fact]
    public void ExtractToolOutput_Boolean_ReturnsTitleCase()
    {
        // .NET JsonElement.ToString() returns "True" not "true"
        var json = JsonDocument.Parse("true").RootElement;
        var result = ClaudeProcess.ExtractToolOutput(json);
        Assert.Equal("True", result);
    }
}
