using System;
using System.Text.Json.Serialization;

namespace LedgerQuant.LiveCapture;

internal sealed class CaptureObservation
{
    [JsonPropertyName("message_id")]
    public Guid MessageId { get; init; }

    [JsonPropertyName("feed_id")]
    public string FeedId { get; init; } = string.Empty;

    [JsonPropertyName("session_id")]
    public Guid SessionId { get; init; }

    [JsonPropertyName("sequence")]
    public long Sequence { get; init; }

    [JsonPropertyName("source")]
    public string Source { get; init; } = "ctrader";

    [JsonPropertyName("broker")]
    public string Broker { get; init; } = string.Empty;

    [JsonPropertyName("environment")]
    public string Environment { get; init; } = string.Empty;

    [JsonPropertyName("account_id")]
    public string AccountId { get; init; } = string.Empty;

    [JsonPropertyName("symbol")]
    public string Symbol { get; init; } = string.Empty;

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("event_at")]
    public DateTimeOffset? EventAt { get; init; }

    [JsonPropertyName("observed_at")]
    public DateTimeOffset ObservedAt { get; init; }

    [JsonPropertyName("bid")]
    public double? Bid { get; init; }

    [JsonPropertyName("ask")]
    public double? Ask { get; init; }

    [JsonPropertyName("buy_percentage")]
    public double? BuyPercentage { get; init; }

    [JsonPropertyName("sell_percentage")]
    public double? SellPercentage { get; init; }

    [JsonPropertyName("sentiment_trigger")]
    public string? SentimentTrigger { get; init; }

    [JsonPropertyName("cbot_version")]
    public string CbotVersion { get; init; } = string.Empty;
}
