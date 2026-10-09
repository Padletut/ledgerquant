using System;
using System.Text;

namespace LedgerQuant.LiveCapture;

internal static class CaptureFeedId
{
    public static string Create(string prefix, string symbolName)
    {
        if (string.IsNullOrEmpty(prefix) || prefix[^1] != '_')
            throw new ArgumentException("Feed ID prefix must end with '_'");
        foreach (var character in prefix)
        {
            if (character is not (>= 'A' and <= 'Z' or >= 'a' and <= 'z' or
                                  >= '0' and <= '9' or '_' or '-'))
                throw new ArgumentException("Feed ID prefix contains an invalid character");
        }
        if (string.IsNullOrWhiteSpace(symbolName))
            throw new ArgumentException("Capture symbol is empty");

        var result = new StringBuilder(prefix);
        foreach (var value in Encoding.UTF8.GetBytes(symbolName))
        {
            if (value is >= (byte)'A' and <= (byte)'Z')
                result.Append((char)(value + ('a' - 'A')));
            else if (value is >= (byte)'a' and <= (byte)'z' or >= (byte)'0' and <= (byte)'9')
                result.Append((char)value);
            else
                result.Append('_').Append(value.ToString("x2"));
        }
        if (result.Length > 100)
            throw new ArgumentException("Derived Feed ID exceeds the 100-character protocol limit");
        return result.ToString();
    }
}
