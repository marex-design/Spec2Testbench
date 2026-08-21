"""Native ngspice result helpers used by deterministic measurement backends.

This reconstruction keeps WRDATA parsing deliberately small and explicit.  It
never fabricates values: malformed or insufficient datasets raise ValueError.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np


def load_wrdata(path: str | Path) -> dict[str, np.ndarray]:
    data=np.loadtxt(Path(path), ndmin=2)
    if data.ndim != 2 or data.shape[0] == 0:
        raise ValueError("EMPTY_WRDATA")
    return {"data": data}


def _column(data: np.ndarray, index: int) -> np.ndarray:
    if index < 0 or index >= data.shape[1]:
        raise ValueError("WRDATA_COLUMN_OUT_OF_RANGE")
    return np.asarray(data[:,index])


def _transfer_series(parsed: dict[str,np.ndarray], request: dict[str,Any]) -> np.ndarray:
    data=np.asarray(parsed["data"])
    if data.ndim != 2 or data.shape[1] < 5:
        raise ValueError("INSUFFICIENT_AC_DATA")
    ir=int(request.get("in_real_column",1)); ii=int(request.get("in_imag_column",2))
    orc=int(request.get("out_real_column",3)); oi=int(request.get("out_imag_column",4))
    vin=_column(data,ir)+1j*_column(data,ii); vout=_column(data,orc)+1j*_column(data,oi)
    return np.divide(vout,vin,out=np.full_like(vout,np.nan+0j,dtype=np.complex128),where=np.abs(vin)>0)


def _transfer_db_series(parsed: dict[str,np.ndarray], request: dict[str,Any]) -> np.ndarray:
    ratio=np.abs(_transfer_series(parsed,request))
    if ratio.size < 2 or not np.any(np.isfinite(ratio)): raise ValueError("INSUFFICIENT_AC_DATA")
    return 20*np.log10(np.maximum(ratio,1e-30))

def _differential_transfer_series(
    parsed: dict[str, np.ndarray],
    request: dict[str, Any],
) -> np.ndarray:
    data = np.asarray(parsed["data"])

    if data.ndim != 2 or data.shape[1] < 7:
        raise ValueError("INSUFFICIENT_DIFFERENTIAL_AC_DATA")

    ipr = int(request.get("in_pos_real_column", 1))
    ipi = int(request.get("in_pos_imag_column", 2))
    inr = int(request.get("in_neg_real_column", 3))
    ini = int(request.get("in_neg_imag_column", 4))
    outr = int(request.get("out_real_column", 5))
    outi = int(request.get("out_imag_column", 6))

    vin_pos = _column(data, ipr) + 1j * _column(data, ipi)
    vin_neg = _column(data, inr) + 1j * _column(data, ini)
    vout = _column(data, outr) + 1j * _column(data, outi)

    vid = vin_pos - vin_neg

    return np.divide(
        vout,
        vid,
        out=np.full_like(vout, np.nan + 0j, dtype=np.complex128),
        where=np.abs(vid) > 0,
    )





def compute_differential_gain_db(parsed, request):
    transfer = _differential_transfer_series(parsed, request)

    magnitude = np.abs(transfer)

    if magnitude.size == 0 or not np.any(np.isfinite(magnitude)):
        raise ValueError("INSUFFICIENT_DIFFERENTIAL_AC_DATA")

    data = np.asarray(parsed["data"])
    frequency = np.asarray(data[:, 0], dtype=float)

    reference_frequency = float(
        request.get("reference_frequency_hz", 1000.0)
    )

    if frequency.size != magnitude.size:
        raise ValueError("DIFFERENTIAL_AC_FREQUENCY_SIZE_MISMATCH")

    valid = np.isfinite(frequency) & np.isfinite(magnitude)

    if not np.any(valid):
        raise ValueError("NO_VALID_DIFFERENTIAL_AC_POINT")

    valid_indices = np.flatnonzero(valid)

    local_index = int(
        np.argmin(
            np.abs(
                frequency[valid_indices]
                - reference_frequency
            )
        )
    )

    index = int(valid_indices[local_index])

    value = magnitude[index]

    if not np.isfinite(value) or value <= 0:
        raise ValueError("INVALID_DIFFERENTIAL_GAIN")

    return float(20.0 * np.log10(value))

def compute_dc_gain_db(parsed,request):
    db=_transfer_db_series(parsed,request); return float(db[0])

def compute_lowpass_attenuation_db(parsed,request):
    db=_transfer_db_series(parsed,request); return float(db[0]-db[-1])

def compute_lowpass_monotonicity_percent(parsed,request):
    db=_transfer_db_series(parsed,request)
    if db.size<3: raise ValueError("INSUFFICIENT_AC_DATA")
    return float(100*np.mean(np.diff(db)<=0.5))

def compute_highpass_attenuation_db(parsed,request):
    db=_transfer_db_series(parsed,request); return float(db[-1]-db[0])

def compute_highpass_monotonicity_percent(parsed,request):
    db=_transfer_db_series(parsed,request)
    if db.size<3: raise ValueError("INSUFFICIENT_AC_DATA")
    return float(100*np.mean(np.diff(db)>=-0.5))

def compute_bandpass_peak_separation_db(parsed,request):
    db=_transfer_db_series(parsed,request)
    if db.size<5: raise ValueError("INSUFFICIENT_AC_DATA")
    i=int(np.nanargmax(db))
    if i==0 or i==db.size-1: raise ValueError("BANDPASS_PEAK_NOT_INTERIOR")
    return float(min(db[i]-np.mean(db[:i]),db[i]-np.mean(db[i+1:])))

def compute_bandstop_notch_depth_db(parsed,request):
    db=_transfer_db_series(parsed,request)
    if db.size<5: raise ValueError("INSUFFICIENT_AC_DATA")
    i=int(np.nanargmin(db))
    if i==0 or i==db.size-1: raise ValueError("BANDSTOP_NOTCH_NOT_INTERIOR")
    return float(min(np.mean(db[:i])-db[i],np.mean(db[i+1:])-db[i]))


WRDATA_EXTRACTORS={
    "dc_gain_db": compute_dc_gain_db,
    "differential_gain_db": compute_differential_gain_db,
    "lowpass_attenuation_db": compute_lowpass_attenuation_db,
    "lowpass_monotonicity_percent": compute_lowpass_monotonicity_percent,
    "highpass_attenuation_db": compute_highpass_attenuation_db,
    "highpass_monotonicity_percent": compute_highpass_monotonicity_percent,
    "bandpass_peak_separation_db": compute_bandpass_peak_separation_db,
    "bandstop_notch_depth_db": compute_bandstop_notch_depth_db,
}
