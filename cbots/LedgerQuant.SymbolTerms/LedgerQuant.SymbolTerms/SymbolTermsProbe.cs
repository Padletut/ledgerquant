using System.Globalization;
using System.Text.Json;
using cAlgo.API;

namespace LedgerQuant.SymbolTerms;

// Reads the broker's terms for the backtested symbol and prints them once.
// No orders, no file or network access, and no account balances or identifiers.
[Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
public sealed class SymbolTermsProbe : Robot
{
    private const string Version = "symbol-terms-0.1.0";

    protected override void OnStart()
    {
        var values = new Dictionary<string, object?>();
        var errors = new Dictionary<string, string>();

        void Read(string key, Func<object?> getter)
        {
            try
            {
                var value = getter();
                if (value is double n && !double.IsFinite(n))
                    throw new InvalidOperationException("nonfinite");
                values[key] = value;
            }
            catch (Exception error)
            {
                values[key] = null;
                errors[key] = error.GetType().Name;
            }
        }

        values["schema"] = "symbol_terms/1";
        values["probe_version"] = Version;
        values["read_at_utc"] = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
        values["is_backtesting"] = IsBacktesting;
        Read("broker", () => Account.BrokerName);
        Read("is_live", () => Account.IsLive);
        Read("symbol", () => Symbol.Name);
        Read("base_asset", () => Symbol.BaseAsset.Name);
        Read("quote_asset", () => Symbol.QuoteAsset.Name);
        Read("digits", () => Symbol.Digits);
        Read("pip_size", () => Symbol.PipSize);
        Read("tick_size", () => Symbol.TickSize);
        Read("lot_size", () => Symbol.LotSize);
        Read("minimum_units", () => Symbol.VolumeInUnitsMin);
        Read("step_units", () => Symbol.VolumeInUnitsStep);
        Read("maximum_units", () => Symbol.VolumeInUnitsMax);
        Read("commission", () => Symbol.Commission);
        Read("commission_type", () => Symbol.CommissionType.ToString());
        Read("minimum_commission", () => Symbol.MinCommission);
        Read("minimum_commission_type", () => Symbol.MinCommissionType.ToString());
        Read("pnl_conversion_fee_rate", () => Symbol.PnLConversionFeeRate);
        Read("swap_long", () => Symbol.SwapLong);
        Read("swap_short", () => Symbol.SwapShort);
        Read("swap_calculation_type", () => Symbol.SwapCalculationType.ToString());
        Read("swap_three_day_rollover", () => Symbol.Swap3DaysRollover?.ToString());
        Read("administrative_charge", () => Symbol.AdministrativeCharge);
        Read("minimum_stop_distance", () => Symbol.MinStopLossDistance);
        Read("stop_distance_type", () => Symbol.MinDistanceType.ToString());
        values["errors"] = errors;
        Print("SYMBOL_TERMS " + JsonSerializer.Serialize(values));
        Stop();
    }
}
